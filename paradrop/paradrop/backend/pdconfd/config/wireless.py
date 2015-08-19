import heapq
import ipaddress
import os
import string
import subprocess
from pprint import pprint

from pdtools.lib.output import out
from paradrop.lib.utils import pdosq

from .base import ConfigObject
from .command import Command


# Command priorities, lower numbers executed first.
PRIO_CREATE_IFACE = 10
PRIO_CONFIG_IFACE = 20
PRIO_START_DAEMON = 30
PRIO_ADD_IPTABLES = 40
PRIO_DELETE_IFACE = 50


def isHexString(data):
    """
    Test if a string contains only hex digits.
    """
    return all(c in string.hexdigits for c in data)


class ConfigWifiDevice(ConfigObject):
    typename = "wifi-device"

    options = [
        {"name": "type", "type": str, "required": True, "default": None},
        {"name": "channel", "type": int, "required": True, "default": 1}
    ]

    def commands(self, allConfigs):
        commands = list()
        return commands


class ConfigWifiIface(ConfigObject):
    typename = "wifi-iface"

    options = [
        {"name": "device", "type": str, "required": True, "default": None},
        {"name": "mode", "type": str, "required": True, "default": "ap"},
        {"name": "ssid", "type": str, "required": True, "default": "Paradrop"},
        {"name": "network", "type": str, "required": True, "default": "lan"},
        {"name": "encryption", "type": str, "required": False, "default": None},
        {"name": "key", "type": str, "required": False, "default": None}
    ]

    def commands(self, allConfigs):
        commands = list()

        if self.mode == "ap":
            pass
        elif self.mode == "sta":
            # TODO: Implement "sta" mode.

            # We only need to set the channel in "sta" mode.  In "ap" mode,
            # hostapd will take care of it.
            #cmd = ["iw", "dev", wifiDevice.name, "set", "channel",
            #       str(wifiDevice.channel)]

            #commands.append(Command(Command.PRIO_CREATE_IFACE, cmd, self))
            raise Exception("WiFi sta mode not implemented")
        else:
            raise Exception("Unsupported mode ({}) in config {} {}".format(
                self.mode, self.typename, self.name))

        # Look up the wifi-device section.
        wifiDevice = self.lookup(allConfigs, "wifi-device", self.device)

        # Look up the interface section.
        interface = self.lookup(allConfigs, "interface", self.network)

        if interface.config_ifname == wifiDevice.name:
            # This interface is using the physical device directly (eg. wlan0).
            self.vifName = None
            ifname = wifiDevice.name
        else:
            # This interface is a virtual one (eg. foo.wlan0 using wlan0).
            self.vifName = interface.config_ifname
            ifname = self.vifName

            # Command to create the virtual interface.
            cmd = ["iw", "dev", wifiDevice.name, "interface", "add",
                   self.vifName, "type", "__ap"]
            commands.append(Command(Command.PRIO_CREATE_IFACE, cmd, self))

        outputPath = "{}/hostapd-{}.conf".format(
            self.manager.writeDir, self.name)
        with open(outputPath, "w") as outputFile:
            # Write our informative header block.
            outputFile.write("#" * 80 + "\n")
            outputFile.write("# hostapd configuration file generated by "
                             "pdconfd\n")
            outputFile.write("# Source: {}\n".format(self.source))
            outputFile.write("# Section: config {} {}\n".format(
                self.typename, self.name))
            outputFile.write("#" * 80 + "\n")

            # Write essential options.
            outputFile.write("interface={}\n".format(ifname))
            outputFile.write("ssid={}\n".format(self.ssid))
            outputFile.write("channel={}\n".format(wifiDevice.channel))

            # Optional encryption options.
            if self.encryption is None or self.encryption == "none":
                pass
            elif self.encryption == "psk2":
                outputFile.write("wpa=1\n")
                # If key is a 64 character hex string, then treat it as the PSK
                # directly, else treat it as a passphrase.
                if len(self.key) == 64 and isHexString(self.key):
                    outputFile.write("wpa_psk={}\n".format(self.key))
                else:
                    outputFile.write("wpa_passphrase={}\n".format(self.key))
            else:
                out.warn("Encryption type {} not supported (supported: "
                         "none|psk2)".format(self.encryption))
                raise Exception("Encryption type not supported")

        self.pidFile = "{}/hostapd-{}.pid".format(
            self.manager.writeDir, self.name)

        cmd = ["/apps/bin/hostapd", "-P", self.pidFile, "-B", outputPath]
        commands.append(Command(Command.PRIO_START_DAEMON, cmd, self))

        return commands

    def undoCommands(self, allConfigs):
        commands = list()

        try:
            with open(self.pidFile, "r") as inputFile:
                pid = inputFile.read().strip()
            cmd = ["kill", pid]
            commands.append(Command(Command.PRIO_START_DAEMON, cmd, self))
        except:
            # No pid file --- maybe it was not running?
            out.warn("File not found: {}\n".format(
                self.pidFile))

        # Delete our virtual interface.
        if self.vifName is not None:
            cmd = ["iw", "dev", self.vifName, "del"]
            commands.append(Command(Command.PRIO_DELETE_IFACE, cmd, self))

        return commands
