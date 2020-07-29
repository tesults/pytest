# -*- coding: utf-8 -*-
import configparser
import os
import sys
import time

import attr
import pytest
import tesults


@attr.s(slots=True, hash=True)
class Plugin:
    inifile = attr.ib()
    build_target = attr.ib()
    build_name = attr.ib()
    build_result = attr.ib()
    build_desc = attr.ib()
    build_reason = attr.ib()
    files_path = attr.ib()
    no_suites = attr.ib(default=False)
    # Internal attributes
    build_token = attr.ib(default=None, repr=False)
    testcases = attr.ib(default=attr.Factory(list), hash=False, repr=False)
    in_flight = attr.ib(default=attr.Factory(dict), hash=False, repr=False)

    def __attrs_post_init__(self):
        if self.build_result not in ("pass", "fail", "unknown"):
            self.build_result = "unknown"
        self.discover_token()

    @property
    def disabled(self):
        return self.build_target is None

    def discover_token(self):
        if self.disabled:
            return
        self.build_token = self.build_target
        # Let's see if this is a target name and in that case try to get the token
        if self.inifile is not None and os.path.exists(self.inifile):
            # Let's load pytest.ini to see if we can find a tesults section
            parser = configparser.ConfigParser()
            parser.read(self.inifile)
            try:
                tesults_section = parser["tesults"]
            except KeyError:
                return

            # Let's try to get a target from the tesults section
            try:
                build_token = tesults_section[self.build_target]
                if build_token:
                    self.build_token = build_token
            except KeyError:
                return

    def friendly_result(self, outcome):
        """
        Converts pytest test outcome to a tesults friendly result (for example pytest uses 'passed', tesults uses 'pass')
        """
        if outcome == "passed":
            return "pass"
        elif outcome == "failed":
            return "fail"
        else:
            return "unknown"

    def reason_for_failure(self, report):
        """
        Extracts test failure reason
        """
        if report.outcome == "passed":
            return ""
        else:
            return report.longreprtext

    def params_for_test(self, item):
        parametrize = None
        try:
            parametrize = item.get_marker("parametrize")
        except AttributeError:
            # No get_marker in pytest 4
            pass
        if parametrize is None:
            try:
                parametrize = item.get_closest_marker("parametrize")
            except AttributeError:
                # No get_closest_marker in pytest 3
                pass
        if parametrize:
            index = 0
            paramKeys = []
            while index < len(parametrize.args):
                keys = parametrize.args[index]
                keys = keys.split(",")
                for key in keys:
                    paramKeys.append(key)
                index = index + 2
            params = {}
            values = item.name.split("[")
            if len(values) > 1:
                values = values[1]
                values = values[:-1]  # removes ']'
                valuesSplit = values.split("-")  # values now separated
                if len(valuesSplit) > len(paramKeys):
                    params["[" + "-".join(paramKeys) + "]"] = "[" + values + "]"
                else:
                    for key in paramKeys:
                        if len(valuesSplit) > 0:
                            params[key] = valuesSplit.pop(0)
                return params
            else:
                return None
        else:
            return None

    def files_for_test(self, suite, name):
        if self.files_path is None:
            return
        files = []
        if suite is None:
            suite = ""
        path = os.path.join(self.files_path, suite, name)
        if os.path.isdir(path):
            for dirpath, dirnames, filenames in os.walk(path):
                for fname in filenames:
                    if fname != ".DS_Store":  # Exclude os files
                        files.append(os.path.join(path, fname))
        return files

    def start_testcase(self, item):
        if self.disabled:
            return
        self.in_flight[item.nodeid] = {"name": item.name, "start": int(round(time.time() * 1000))}

    def stop_testcase(self, item):
        if self.disabled:
            return
        self.in_flight[item.nodeid]["end"] = int(round(time.time() * 1000))

    def record_testcase(self, item, report):
        if report.when != "teardown":
            return

        try:
            testcase = self.in_flight.pop(item.nodeid)
        except KeyError:
            return

        name = item.name
        suite = None
        try:
            suite = item.get_marker("suite")
            if suite:
                suite = suite.args[0]  # extract val from marker
        except AttributeError:
            # no get_marker if pytest 4
            pass
        if suite is None:
            try:
                suite = item.get_closest_marker("suite")
                if suite:
                    suite = suite.args[0]  # extract val from marker
            except AttributeError:
                # no get_closest_marker in pytest 3
                pass
        if suite is None:
            if self.no_suites is False:
                suite = str(item.parent.name)
                suite = suite.rpartition("/")[2]
                suite = suite.rpartition(".py")[0]

        testcase.update(
            {
                "result": self.friendly_result(report.outcome),
                "reason": self.reason_for_failure(report),
            }
        )
        if suite:
            testcase["suite"] = suite
        files = self.files_for_test(suite, name)
        if files:
            testcase["files"] = files
        params = self.params_for_test(item)
        if params:
            testcase["params"] = params
            testname = item.name.split("[")
            if testname:
                testcase["name"] = testname[0]
        description = None
        try:
            description = item.get_marker("description")
        except AttributeError:
            # no get_marker if pytest 4
            pass
        if description is None:
            try:
                description = item.get_closest_marker("description")
            except AttributeError:
                # no get_closest_marker in pytest 3
                pass

        if description:
            testcase["desc"] = description.args[0]

        try:
            markers = item.iter_markers()
            for marker in markers:
                if marker.name in (
                    "parametrize",
                    "filterwarnings",
                    "skip",
                    "skipif",
                    "usefixtures",
                    "xfail",
                    "suite",
                ):
                    continue
                if marker.name in ("description", "desc"):
                    testcase["desc"] = marker.args[0]
                    continue
                try:
                    testcase["_{}".format(marker.name)] = marker.args[0]
                except IndexError:
                    testcase["_{}".format(marker.name)] = marker.name
        except AttributeError:
            pass
        self.testcases.append(testcase)

    def upload_results(self):
        if not self.testcases:
            # Report no test cases
            return

        build_case = {"name": self.build_name, "result": self.build_result, "suite": "[build]"}
        if self.build_desc:
            build_case["desc"] = self.build_desc
        if self.build_reason:
            build_case["reason"] = self.build_reason
        build_files = self.files_for_test(build_case["suite"], self.build_name)
        if build_files:
            build_case["files"] = build_files

        self.testcases.append(build_case)

        data = {"target": self.build_token, "results": {"cases": self.testcases}}
        return tesults.results(data)


def pytest_addoption(parser):
    # Args:
    #   --tesults-files
    #   --tesults-nosuites, for disabling setting suite as module name if no suite supplied
    #   --tesults-build-name (optional)
    #   --tesults-build-result (optional)
    #   --tesults-build-description (optional)
    #   --tesults-build-reason (optional)
    group = parser.getgroup("tesults")
    group.addoption(
        "--tesults-target",
        action="store",
        dest="target",
        default=None,
        help="Set tesults target token. Required for tesults upload.",
    )
    group.addoption(
        "--tesults-files",
        action="store",
        dest="filespath",
        default=None,
        help="Path to files for test cases",
    )
    group.addoption(
        "--tesults-nosuites",
        action="store_true",
        help="Disable tesults from setting module name as suite if no suite supplied.",
    )
    group.addoption(
        "--tesults-build-name",
        action="store",
        dest="buildname",
        default=None,
        help="Set the build for tesults.",
    )
    group.addoption(
        "--tesults-build-result",
        action="store",
        dest="buildresult",
        default="unknown",
        help="Set the build result for tesults. One of [pass, fail, unknown]",
    )
    group.addoption(
        "--tesults-build-description",
        action="store",
        dest="builddesc",
        default=None,
        help="Set the build description",
    )
    group.addoption(
        "--tesults-build-reason",
        action="store",
        dest="buildreason",
        default=None,
        help="Set a build fail reason",
    )


def pytest_configure(config):
    inifile = config.inifile
    if inifile:
        inifile = os.path.join(config.rootdir, str(inifile))
    build_target = config.getoption("--tesults-target")
    build_name = config.getoption("--tesults-build-name")
    build_desc = config.getoption("--tesults-build-description")
    build_reason = config.getoption("--tesults-build-reason")
    build_result = config.getoption("--tesults-build-result")
    no_suites = config.getoption("--tesults-nosuites")
    files_path = config.getoption("--tesults-files")
    if build_result not in ("pass", "fail", "unknown"):
        build_result = "unknown"

    plugin = Plugin(
        inifile=inifile,
        build_target=build_target,
        build_name=build_name,
        build_result=build_result,
        build_desc=build_desc,
        build_reason=build_reason,
        no_suites=no_suites,
        files_path=files_path,
    )
    config.pluginmanager.register(plugin, "tesults_reporter")


def pytest_unconfigure(config):
    plugin = config.pluginmanager.getplugin("tesults_reporter")
    if plugin:
        # Unregister
        config.pluginmanager.unregister(plugin, "tesults_reporter")


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    # execute all other hooks to obtain the report object
    report = (yield).get_result()

    plugin = item.config.pluginmanager.getplugin("tesults_reporter")
    if plugin and not plugin.disabled:
        if report.when == "setup":
            plugin.start_testcase(item)
        if report.when == "teardown":
            plugin.stop_testcase(item)
            plugin.record_testcase(item, report)


@pytest.hookimpl(trylast=True)
def pytest_terminal_summary(terminalreporter, exitstatus, config):
    plugin = config.pluginmanager.getplugin("tesults_reporter")
    if plugin:
        ret = plugin.upload_results()
        terminalreporter.ensure_newline()
        terminalreporter.section("TResults Upload Info", sep="=", bold=True)
        for key, value in ret.items():
            terminalreporter.line("{}: {}".format(key.capitalize(), value))
