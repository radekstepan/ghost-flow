/*
 * QT WebChannel JavaScript Library v5.15.2
 * (Standard library required for Python-JS communication)
 */
"use strict";

var QWebChannel = function(transport, initCallback)
{
    if (typeof transport !== "object" || typeof transport.send !== "function") {
        console.error("The QWebChannel expects a transport object with a send function and onmessage callback property. Given is: transport: " + typeof(transport) + ", transport.send: " + typeof(transport.send));
        return;
    }

    var channel = this;
    this.transport = transport;

    this.send = function(data)
    {
        if (typeof(data) !== "string") {
            data = JSON.stringify(data);
        }
        channel.transport.send(data);
    }

    this.transport.onmessage = function(message)
    {
        var data = message.data;
        if (typeof data === "string") {
            data = JSON.parse(data);
        }
        switch (data.type) {
            case QWebChannelMessageTypes.signal:
                channel.handleSignal(data);
                break;
            case QWebChannelMessageTypes.response:
                channel.handleResponse(data);
                break;
            case QWebChannelMessageTypes.propertyUpdate:
                channel.handlePropertyUpdate(data);
                break;
            default:
                console.error("invalid message received:", message.data);
                break;
        }
    }

    this.execCallbacks = {};
    this.execId = 0;
    this.exec = function(data, callback)
    {
        if (!callback) {
            // if no callback is given, send directly
            channel.send(data);
            return;
        }
        if (channel.execId === Number.MAX_VALUE) {
            // wrap
            channel.execId = Number.MIN_VALUE;
        }
        var id = channel.execId++;
        channel.execCallbacks[id] = callback;
        data.id = id;
        channel.send(data);
    };

    this.objects = {};

    this.handleSignal = function(message)
    {
        var object = channel.objects[message.object];
        if (object) {
            object.signalEmitted(message.signal, message.args);
        } else {
            console.warn("Unhandled signal: " + message.object + "::" + message.signal);
        }
    }

    this.handleResponse = function(message)
    {
        if (!message.hasOwnProperty("id")) {
            console.error("Invalid response message received: ", message);
            return;
        }
        channel.execCallbacks[message.id](message.data);
        delete channel.execCallbacks[message.id];
    }

    this.handlePropertyUpdate = function(message)
    {
        for (var i in message.data) {
            var data = message.data[i];
            var object = channel.objects[data.object];
            if (object) {
                object.propertyUpdate(data.signals, data.properties);
            } else {
                console.warn("Unhandled property update: " + data.object + "::" + data.signal);
            }
        }
        channel.execCallbacks[message.id](message.data);
        delete channel.execCallbacks[message.id];
    }

    this.debug = function(message)
    {
        channel.send({type: QWebChannelMessageTypes.debug, data: message});
    };

    channel.exec({type: QWebChannelMessageTypes.init}, function(data) {
        for (var objectName in data) {
            var object = new QObject(objectName, data[objectName], channel);
        }
        // now unwrap properties to remove the wrapper objects
        for (var objectName in channel.objects) {
            var object = channel.objects[objectName];
            object.unwrapProperties();
        }
        if (initCallback) {
            initCallback(channel);
        }
    });
};

var QWebChannelMessageTypes = {
    signal: 1,
    propertyUpdate: 2,
    init: 3,
    idle: 4,
    debug: 5,
    invokeMethod: 6,
    connectToSignal: 7,
    disconnectFromSignal: 8,
    setProperty: 9,
    response: 10,
};

var QObject = function(name, data, webChannel)
{
    this.__id__ = name;
    webChannel.objects[name] = this;

    // List of callbacks that get invoked upon signal emission
    this.__objectSignals__ = {};

    // Cache of all properties, updated when a notify signal is emitted
    this.__propertyCache__ = {};

    var object = this;

    // ----------------------------------------------------------------------
    // Property binding
    // ----------------------------------------------------------------------

    this.unwrapProperties = function()
    {
        for (var propertyIndex in data.properties) {
            object.unwrapProperty(propertyIndex, data.properties[propertyIndex]);
        }
    }

    this.unwrapProperty = function(propertyIndex, value)
    {
        Object.defineProperty(object, propertyIndex, {
            configurable: true,
            get: function () {
                var propertyValue = object.__propertyCache__[propertyIndex];
                if (propertyValue === undefined) {
                    // This re-renders the property. 
                    // This value is the initial value as found in the web channel initialization
                    // if the property is not cached (because it was not updated yet)
                    return value;
                }
                return propertyValue;
            },
            set: function (newValue) {
                // Only property updates (from the c++ side) update the property cache
                // Setting a property from the JS side means sending a message to the c++ side
                // to invoke the setter of the property
                if (value === undefined) {
                    console.warn("Property setter called with undefined value for property: " + propertyIndex);
                    return;
                }
                var sessionId = webChannel.exec({
                    type: QWebChannelMessageTypes.setProperty,
                    object: object.__id__,
                    property: propertyIndex,
                    value: newValue
                });
            }
        });
    }

    this.propertyUpdate = function(signals, propertyMap)
    {
        // update property cache
        for (var propertyIndex in propertyMap) {
            var propertyValue = propertyMap[propertyIndex];
            object.__propertyCache__[propertyIndex] = propertyValue;
        }

        for (var signalName in signals) {
            // invokes all callbacks that are connected to the signal
            object.signalEmitted(signalName, signals[signalName]);
        }
    }

    // ----------------------------------------------------------------------
    // Signal Binding
    // ----------------------------------------------------------------------

    this.signalEmitted = function(signalName, signalArgs)
    {
        var connections = object.__objectSignals__[signalName];
        if (connections) {
            connections.forEach(function(callback) {
                callback.apply(callback, signalArgs);
            });
        }
    }

    this.connect = function(signalName, callback)
    {
        if (typeof callback !== "function") {
            console.error("Bad callback given to connect to signal " + signalName);
            return;
        }

        object.__objectSignals__[signalName] = object.__objectSignals__[signalName] || [];
        object.__objectSignals__[signalName].push(callback);

        if (!data.signals[signalName]) {
            // signal connecting is not necessary with raw method signals
            return;
        }

        // Invoke connectToSignal on C++ side
        // This is only required for QObject signals, not for raw signals
        var sessionId = webChannel.exec({
            type: QWebChannelMessageTypes.connectToSignal,
            object: object.__id__,
            signal: signalName
        });
    };

    this.disconnect = function(signalName, callback)
    {
        if (typeof callback !== "function") {
            console.error("Bad callback given to disconnect from signal " + signalName);
            return;
        }
        object.__objectSignals__[signalName] = object.__objectSignals__[signalName] || [];
        var idx = object.__objectSignals__[signalName].indexOf(callback);
        if (idx === -1) {
            console.error("Cannot find connection of signal " + signalName + " to " + callback.name);
            return;
        }
        object.__objectSignals__[signalName].splice(idx, 1);
        if (!data.signals[signalName]) {
            // signal connecting is not necessary with raw method signals
            return;
        }
        var sessionId = webChannel.exec({
            type: QWebChannelMessageTypes.disconnectFromSignal,
            object: object.__id__,
            signal: signalName
        });
    };

    // ----------------------------------------------------------------------
    // Method Binding
    // ----------------------------------------------------------------------

    this.unwrapMethod = function(methodName)
    {
        object[methodName] = function() {
            var args = [];
            var callback;
            for (var i = 0; i < arguments.length; i++) {
                if (typeof arguments[i] === "function") {
                    callback = arguments[i];
                } else {
                    args.push(arguments[i]);
                }
            }

            webChannel.exec({
                "type": QWebChannelMessageTypes.invokeMethod,
                "object": object.__id__,
                "method": methodName,
                "args": args
            }, function(response) {
                if (response !== undefined) {
                    var result = response;
                    if (callback) {
                        callback(result);
                    }
                }
            });
        };
    }

    for (var methodIndex in data.methods) {
        this.unwrapMethod(data.methods[methodIndex][0]);
    }

    // ----------------------------------------------------------------------
    // Signal Wrapper
    // ----------------------------------------------------------------------

    this.unwrapSignal = function(signalName)
    {
        // Use an object to enable easy connectivity
        object[signalName] = {
            connect: function(callback) {
                object.connect(signalName, callback);
            },
            disconnect: function(callback) {
                object.disconnect(signalName, callback);
            }
        };
    }

    for (var signalIndex in data.signals) {
        this.unwrapSignal(data.signals[signalIndex][0]);
    }
};
