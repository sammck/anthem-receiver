/**
 * Hubitat Anthem receiver HTTP Device Driver
 *
 * MIT License
 *
 * Copyright (c) 2023 Samuel J. McKelvie
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in all
 * copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 */
metadata {
    definition(name: "Anthem receiver - HTTP", namespace: "community", author: "Community", importUrl: "https: raw.githubusercontent.com/sammck/anthem-receiver/master/hubitat/anthem-receiver-http.groovy") {
        capability "Initialize"
        capability "Actuator"
        capability "Switch"
        capability "Sensor"
        capability "Refresh"
        attribute "powerStatus", "enum", [ "unknown", "on", "standby", "cooling", "warming", "emergency" ]
    }
}

preferences {
    input "apiServerURI", "text", title: "API Server URI", displayDuringSetup: true
    input "pollingInterval", "number", title: "Polling Interval", description: "in seconds", range: "10..300", defaultValue: 30, displayDuringSetup: true
    input "transitionPollingInterval", "number", title: "Transition Polling Interval", description: "in seconds", range: "1..300", defaultValue: 1, displayDuringSetup: false
    input name: "logEnable", type: "bool", title: "Enable debug logging", defaultValue: true, displayDuringSetup: false
}

Map successfulApiResponse(Map response_data) {
    /* Checks the response JSON data from a Receiver API call.
     * If the response is successful, returns the response data.
     * If the response is unsuccessful, throws an Exception.
     */
    if (response_data.containsKey("error")) {
        if (response_data.containsKey("error_message")) {
            throw new Exception("Anthem receiver API error: ${response_data.error}: ${response_data.error_message}")
        } else {
            throw new Exception("Anthem receiver API error: ${response_data.error}")
        }
    }
    if (response_data.containsKey("status") && response_data.status != "OK") {
        throw new Exception("Anthem receiver API error: Unsuccessful status '${response_data.status}'")
    }
    if (!response_data.containsKey("status")) {
        response_data.status = "OK"
    }
    return response_data
}

def updatePowerStatus(String rawPowerStatus) {
    /* Updates the driver state from a detected receiver power status.
     * If the power status has changed, sends "powerStatus" and "switch" events.
     * For the purposes of the "switch" capabiility, the receiver is considered
     * "on" if it is in "On" or "Warming" mode, and "off" otherwise.
     */
    if ( rawPowerStatus != null) {
        state.rawPowerStatus =  rawPowerStatus
        currentPowerState = device.currentValue("powerStatus")
        newPowerState = rawPowerStatus.toLowerCase()
        if (newPowerState != currentPowerState) {
            if (logEnable) log.debug "Got updated power status  ${newPowerState}"
            sendEvent(
                name: "powerStatus",
                value: newPowerState,
                descriptionText: "${device.displayName} powerStatus set to ${newPowerState}",
                isStateChange: true
              )
        }
        String currentSwitchState = device.currentValue("switch")
        String newSwitchState = (newPowerState == "on" || newPowerState == "warming") ? "on" : "off"
        if (newSwitchState != currentSwitchState) {
            sendEvent(name: "switch", value: newSwitchState, isStateChange: true)
        }
    }
    schedulePolling()
}

def updateFromApiResponse(String apiPath, Map response) {
    /* Updates the device state from the response JSON data for a REST API call.
       receiver command. Used to record power status changes
       detectable via "power_status.query", "on", "off", "on_start", "off_start",
       and "power_status_wait" commands.
       If the API does not return useful data or indicates a failure, has no effect.
     */
    if (    apiPath == "v1/execute/power_status.query" ||
            apiPath == "v1/execute/on" ||
            apiPath == "v1/execute/off" ||
            apiPath == "v1/execute/start_on" ||
            apiPath == "v1/execute/start_off" ||
            apiPath == "v1/execute/power_status_wait"
            ) {
        if (response.containsKey("response_str")) {
            String rawPowerStatus = response.response_str
            updatePowerStatus( rawPowerStatus)
        } else {
            updatePowerStatus(null)
        }
    }
}

def onAsyncApiComplete(response, Map data) {
    /* HTTP Callback function for asynchronous Receiver API calls.
     * On success, calls the asyncApi() callbackMethod with the response JSON data.
     * On failure, calls the asyncApi() callbackMethod with a constructed error data object.
     * If the callbackMethod is null, does not make a callback.
     *
     * Regardless of whether the callbackMethod is null, if the response contains
     * updated device state data (e.g., power state info), updates the driver state
     * to reflect the change.
     */
    String apiPath = data.apiPath
    Map apiData = data.apiData
    Closure callbackMethod = data.callbackMethod
    Map responseData = null
    if (logEnable) log.debug "onAsyncApiComplete: apiPath=${apiPath}, status=${response.status}"
    if (response.status == 200) {
        if (response.data instanceof Map) {
            responseData = response.data
        } else if(response.data instanceof String) {
            responseData = parseJson(response.data)
        } else {
            responseData = [:]
        }
        if (!responseData.containsKey("status")) {
            if (!responseData.containsKey("error")) {
                responseData.status = "OK"
            } else {
                responseData.status = "FAIL"
            }
        }
        updateFromApiResponse(apiPath, responseData)
    } else {
        log.warn "onAsyncApiComplete: HTTP GET failed: apiPath=${apiPath}, status=${response.status}"
        responseData = [
            status: "FAIL",
            http_status: response.status,
            error: "HttpError",
            error_message: "HTTP GET failed: apiPath=${apiPath}, status=${response.status}",
        ]
    }
    log.debug "onAsyncApiComplete: responseData=${responseData}"
    if (callbackMethod != null) {
        callbackMethod(responseData, apiData)
    }
}

def asyncApi(String apiPath, Map data = null, Closure callbackMethod=null) {
    /* Asynchronous Receiver HTTP API call.
     * Invokes an HTTP GET request to the receiver REST server with the specified API path.
     *     apiPath: The API subpath path to invoke; e.g. 'v1/execute/power.on'.
     *     data: An optional Map object that will be passed along to the callback
     *     callbackMethod: A closure that will be called when the API call completes. If null,
     *         no callback will be invoked.
     *         The closure will be passed two arguments:
     *             response: A Map containing the response JSON data. The
     *                       "status" key will be set to "OK" or "FAIL".
     *                       "error" and "error_message" keys will be set if
     *                       the response was unsuccessful.
     *             data: The Map object passed in the 'data' argument.
     *
     * Regardless of whether the callbackMethod is null, if the response contains
     * updated device state data (e.g., power state info), updates the driver state
     * to reflect the change.
     */
    apiUri ="${apiServerURI}/${apiPath}"
    if (logEnable) log.debug "asyncApi: '${apiUri}' starting..."
    params = [
        uri: apiUri,
    ]
    http_data = [
        apiPath: apiPath,
        apiData: data,
        callbackMethod: callbackMethod,
    ]
    asynchttpGet(onAsyncApiComplete, params, http_data)
}

def asyncCommand(String cmd, Map data=null, Closure callbackMethod=null) {
    /* Asynchronous receiver command.
     * Invokes an async API request to the receiver REST server to run the specified
     * receiver command.
     *     cmd: The command to invoke; e.g. 'power.on'.
     *     data: An optional Map object that will be passed along to the callback
     *     callbackMethod: A closure that will be called when the API call completes. If
     *         null, no callback will be invoked.
     *         The closure will be passed two arguments:
     *             response: A Map containing the response JSON data. The
     *                       "status" key will be set to "OK" or "FAIL".
     *                       "error" and "error_message" keys will be set if
     *                       the response was unsuccessful.
     *             data: The Map object passed in the 'data' argument.
     * Regardless of whether the callbackMethod is null, if the response contains
     * updated device state data (e.g., power state info), updates the driver state
     * to reflect the change.
     */
    asyncApi("v1/execute/${cmd}", data, callbackMethod)
}

/* A list of callbacks to be invoked when the receiver power status is returned. If null,
 * no callbacks are pending.
 * Each element in the list is a Map containing:
 *     callbackMethod: The callback closure to invoke
 *     data: The Map object passed in the 'data' argument to the asyncPowerStatusWait() call
 */
List<Map> asyncPowerStatusCallbacks = null

/* True if an asyncPowerStatus() call is in progress. */
boolean asyncPowerStatusInProgress = false

def asyncPowerStatus(Map data=null, Closure callbackMethod=null) {
    /* Asynchronous receiver power status query.
     * Multiple overlapping calls will be coalesced.
     * Invokes an async API request to determine the receiver's power status.
     *     data: An optional Map object that will be passed along to the callback
     *     callbackMethod: A closure that will be called when the API call completes. If
     *         null, no callback will be invoked.
     *         The closure will be passed three arguments:
     *              rawPowerStatus: The receiver's power status, as a String.
     *                 null:        Unknown power status (the request failed)
     *                 "On":        The receiver is on
     *                 "Standby":   The receiver is in standby (turned off)
     *                 "Cooling":   The receiver is cooling down after being turned off
     *                              and will soon be in "Standby" mode
     *                 "Warming":   The receiver is warming up after being turned on
     *                              and will soon be in "On" mode
     *                 "Emergency": The receiver is in an error state
     *             response: A Map containing the response JSON data. The
     *                       "status" key will be set to "OK" or "FAIL".
     *                       "error" and "error_message" keys will be set if
     *                       the response was unsuccessful.
     *                       The "response_str" key will be set to the receiver's
     *                       power status string on success.
     *             data: The Map object passed in the 'data' argument.
     *
     * Regardless of whether the callbackMethod is null, if the response contains
     * updated device state data (e.g., power state info), updates the driver state
     * to reflect the change.
     */
    if (callbackMethod != null) {
        if (asyncPowerStatusCallbacks == null) {
            asyncPowerStatusCallbacks = []
        }
        asyncPowerStatusCallbacks.add([callbackMethod: callbackMethod, data: data])
    }
    if (!asyncPowerStatusInProgress) {
        asyncPowerStatusInProgress = true
        asyncCommand("power_status.query", data) { response, _data ->
            if (logEnable) log.debug "Completed power status query, response=${response}"
            asyncPowerStatusInProgress = false
            callbacks = asyncPowerStatusCallbacks
            asyncPowerStatusCallbacks = null
            String rawPowerStatus = null
            if (response != null && response.containsKey("response_str")) {
                 rawPowerStatus = response.response_str
            }
            if (callbacks != null) {
                for (Map callback in callbacks) {
                    callbackMethod = callback.callbackMethod
                    data = callback.data
                    callbackMethod(rawPowerStatus, response, _data)
                }
            }
        }
    }
}

/* A list of callbacks to be invoked when the receiver power status becomes stable. If null,
 * no callbacks are pending.
 * Each element in the list is a Map containing:
 *     callbackMethod: The callback closure to invoke
 *     data: The Map object passed in the 'data' argument to the asyncPowerStatusWait() call
 */
List<Map> asyncPowerStatusWaitCallbacks = null

/* True if an asyncPowerStatusWait() call is in progress. */
boolean asyncPowerStatusWaitInProgress = false

def asyncPowerStatusWait(Map data=null, Closure callbackMethod=null) {
    /* Asynchronously waits for the receiver power status to become stable;
     * i.e., not in "Warming" or "Cooling" modes.
     * Note that this call may take considerable time (up to 30 seconds) to
     * complete. Multiple overlapping calls to this function will be coalesced into
     * a single asynchronous API request; when it completes, all callbacks
     * will be invoked.
     *     data: An optional Map object that will be passed along to the callback
     *     callbackMethod: A closure that will be called when the call completes. If
     *         null, no callback will be invoked.
     *         The closure will be passed three arguments:
     *              rawPowerStatus: The receiver's power status, as a String.
     *                 null:        Unknown power status (the request failed)
     *                 "On":        The receiver is on
     *                 "Standby":   The receiver is in standby (turned off)
     *                 "Emergency": The receiver is in an error state
     *             response: A Map containing the response JSON data. The
     *                       "status" key will be set to "OK" or "FAIL".
     *                       "error" and "error_message" keys will be set if
     *                       the response was unsuccessful.
     *                       The "response_str" key will be set to the receiver's
     *                       power status string on success.
     *             data: The Map object passed in the 'data' argument.
     *
     * Regardless of whether the callbackMethod is null, if the response contains
     * updated device state data (e.g., power state info), updates the driver state
     * to reflect the change.
     */
    if (callbackMethod != null) {
        if (asyncPowerStatusWaitCallbacks == null) {
            asyncPowerStatusWaitCallbacks = []
        }
        asyncPowerStatusWaitCallbacks.add([callbackMethod: callbackMethod, data: data])
    }
    if (!asyncPowerStatusWaitInProgress) {
        asyncPowerStatusWaitInProgress = true
        asyncCommand("power_status_wait", data) { response, _data ->
            callbacks = asyncPowerStatusWaitCallbacks
            asyncPowerStatusWaitCallbacks = null
            asyncPowerStatusWaitInProgress = false
            updateFromPowerStatus(response)
            String  rawPowerStatus = null
            if (response.containsKey("response_str")) {
                 rawPowerStatus = response.response_str
            }
            if (callbacks != null) {
                for (Map callback in callbacks) {
                    callbackMethod = callback.callbackMethod
                    data = callback.data
                    callbackMethod( rawPowerStatus, response, _data)
                }
            }
        }
    }
}

def asyncPowerOn(boolean wait_for_final=true, Map data=null, Closure callbackMethod=null) {
    /* Asynchronously turns on the receiver, optionally waiting for it to warm up.
     *
     * If the receiver is cooling down, this command will wait for it to finish
     * cooling down before turning it on.

     * Note that this call may take considerable time (up to 60 seconds) to
     * complete.
     *     wait_for_final: If true, waits for the receiver to finish warming up
     *           before completing
     *     data: An optional Map object that will be passed along to the callback
     *     callbackMethod: A closure that will be called when the call completes. If
     *         null, no callback will be invoked.
     *         The closure will be passed three arguments:
     *              rawPowerStatus: The receiver's power status, as a String.
     *                 null:        Unknown power status (the request failed)
     *                 "On":        The receiver is on
     *                 "Standby":   The receiver is in standby (turned off)
     *                 "Emergency": The receiver is in an error state
     *             response: A Map containing the response JSON data. The
     *                       "status" key will be set to "OK" or "FAIL".
     *                       "error" and "error_message" keys will be set if
     *                       the response was unsuccessful.
     *                       The "response_str" key will be set to the receiver's
     *                       power status string on success.
     *             data: The Map object passed in the 'data' argument.
     *
     * Regardless of whether the callbackMethod is null, if the response contains
     * updated device state data (e.g., power state info), updates the driver state
     * to reflect the change. if wait_for_final is false, will return as soon as
     * the receiver enters "Warming" state, but the receiver power state will
     * continue to be polled at high frequency until it stabilizes.
     */
    String cmd = wait_for_final ? "on" : "start_on"
    asyncCommand(cmd, data) { response, _data ->
        String rawPowerStatus = null
        if (response.containsKey("response_str")) {
            rawPowerStatus = response.response_str
        }
        if (callbackMethod != null) {
            callbackMethod(rawPowerStatus, response, _data)
        }
    }
}

def asyncPowerOff(boolean wait_for_final=true, Map data=null, Closure callbackMethod=null) {
    String cmd = wait_for_final ? "off" : "start_off"
    asyncCommand(cmd, data) { response, _data ->
        String  rawPowerStatus = null
        if (response.containsKey("response_str")) {
             rawPowerStatus = response.response_str
        }
        if (callbackMethod != null) {
            callbackMethod( rawPowerStatus, response, _data)
        }
    }
}

def logsOff() {
    /* Turns off debug logging.
     * Called after 30 minutes if debug logging is enabled.
     */
    log.warn ("Disabling logging after timeout")
      device.updateSetting("logEnable",[value:"false",type:"bool"])
}

def parse(String description) {
    /* Called by Hubitat with raw Zigbee, Z-Wave, LAN data.
     * Not used by this driver.
     */
    if (logEnable) log.debug("parse(${description}")
}

def on() {
    /* Turns on the receiver.
     * implementation of Switch capability
     * Invokes an async API request to turn on the receiver.
     */
    if (logEnable) log.debug "Sending ON command to receiver..."
    asyncPowerOn(wait_for_final=false)
}

def off() {
    /* Turns off the receiver.
     * implementation of Switch capability
     * Invokes an async API request to turn off the receiver.
     */
    if (logEnable) log.debug "Sending OFF command to receiver..."
    asyncPowerOff(wait_for_final=false)
}

def handlePollPower(Closure callbackMethod=null) {
    /* Called at regular intervals to poll the receiver's power status.
     * Invokes an async API request to determine the receiver's power status.
     * If the receiver is warming up or cooling down, polling is done at a high
     * frequency until the receiver's power status stabilizes.
     */
    if (logEnable) log.debug "Polling receiver power status..."
    asyncPowerStatus(data=null) { rawPowerStatus, response, data ->
        if (logEnable) log.debug "Completed polling power status: ${rawPowerStatus}"
        if (callbackMethod != null) {
            callbackMethod()
        }
    }
}

def schedulePolling() {
    nextInterval = pollingInterval
     rawPowerStatus = state.rawPowerStatus
    if ( rawPowerStatus == "Warming" ||  rawPowerStatus == "Cooling") {
        nextInterval = transitionPollingInterval
    }
    runIn(nextInterval, handlePollPower)
}


def updated() {
    /* Called by Hubitat when the device configuration is updated.
     * If debug logging is enabled, turns it off after 30 minutes.
     */
    log.info "updated..."
    log.warn "debug logging is: ${logEnable == true}"
    if (logEnable) runIn(1800, logsOff)
    handlePollPower()
}

def refresh() {
    /* Refreshes the device state from the receiver.
     * implementation of Refresh capability
     * Invokes an async API request to determine the receiver's power status,
     * which will update the device state.
     */
    if (logEnable) log.debug("refresh() starting")
    asyncPowerStatus(data=null) { rawPowerStatus, response, data ->
        if (logEnable) log.debug("refresh() complete")
    }
}

def initialize() {
    /* Called by Hubitat when the device is initialized.
     * Invokes an async API request to update the receiver's power status,
     */
    log.info "initializing..."
    log.warn "debug logging is: ${logEnable == true}"
    state.rawPowerStatus = null
    if (logEnable) runIn(1800, logsOff)
    handlePollPower()
}
