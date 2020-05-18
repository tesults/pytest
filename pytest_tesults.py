# -*- coding: utf-8 -*-

import pytest
import tesults
import sys
import configparser
import os
import time
from _pytest.runner import runtestprotocol


# The data variable holds test results and tesults target information, at the end of test run it is uploaded to tesults for reporting.
data = {
  'target': 'token',
  'results': { 'cases': [] }
}

startTimes = {}

disabled = False
nosuites = False
filespath = None
buildcase = None

def pytest_addoption(parser):
    # Args: 
    #   --tesults-files
    #   --tesults-nosuites, for disabling setting suite as module name if no suite supplied
    #   --tesults-build-name (optional)
    #   --tesults-build-result (optional)
    #   --tesults-build-description (optional)
    #   --tesults-build-reason (optional)
    group = parser.getgroup('tesults')
    group.addoption(
      '--tesults-target',
      action='store',
      dest='target',
      default=None,
      help='Set tesults target token. Required for tesults upload.'
    )
    group.addoption(
      '--tesults-files',
      action='store',
      dest='filespath',
      default=None,
      help='Path to files for test cases'
    )
    group.addoption(
      '--tesults-nosuites',
      action='store_true',
      help='Disable tesults from setting module name as suite if no suite supplied.'
    )
    group.addoption(
      '--tesults-build-name',
      action='store',
      dest='buildname',
      default=None,
      help='Set the build for tesults.'
    )
    group.addoption(
      '--tesults-build-result',
      action='store',
      dest='buildresult',
      default='unknown',
      help='Set the build result for tesults. One of [pass, fail, unknown]'
    )
    group.addoption(
      '--tesults-build-description',
      action='store',
      dest='builddesc',
      default=None,
      help='Set the build description'
    )
    group.addoption(
      '--tesults-build-reason',
      action='store',
      dest='buildreason',
      default=None,
      help='Set a build fail reason'
    )
    

def pytest_configure(config):
    global data
    
    global disabled
    targetKey = None
    targetKey = config.option.target
    if (targetKey is None):
      disabled = True
      return

    global nosuites
    if (config.getoption('--tesults-nosuites')):
      nosuites = True

    targetValue = None
    configFileData = None
    try:
      if (config.inifile):
        inipath = os.path.join(config.rootdir, str(config.inifile))
        configparse = configparser.ConfigParser()
        configparse.read(inipath)
        configFileData = configparse['tesults']
    except ValueError as error:
      print('ValueError in pytest-tesults configuration: ' + str(error))
    
    try:
      if (configFileData):
        targetValue = configFileData[targetKey]
        data['target'] = targetValue
    except ValueError as error:
      print('ValueError in pytest-tesults configuration: ' + str(error))
      raise error
    except KeyError as error:
      print('pytest-tesults configuration: no key for target ' + str(error) + ' found in configuration files, will make target=' + targetKey)

    if (targetKey):
      if (targetValue is None):
        data['target'] = targetKey

    # Files path
    global filespath
    filespath = config.option.filespath

    # Report Build Information (Optional)
    buildname = config.option.buildname
    buildresult = config.option.buildresult
    builddesc = config.option.builddesc
    buildreason = config.option.buildreason
    if (buildresult != 'pass' and buildresult != 'fail'):
        buildresult = 'unknown'
    if (buildname):
      global buildcase
      buildcase = {
        'name': buildname,
        'result': buildresult,
        'suite': '[build]',
      }
      if (builddesc):
        buildcase['desc'] = builddesc
      if (buildreason):
        buildcase['reason'] = buildreason

# Converts pytest test outcome to a tesults friendly result (for example pytest uses 'passed', tesults uses 'pass')
def tesultsFriendlyResult (outcome):
  if (outcome == 'passed'):
    return 'pass'
  elif (outcome == 'failed'):
    return 'fail'
  else:
    return 'unknown'

# Extracts test failure reason
def reasonForFailure (report):
  if report.outcome == 'passed':
    return ''
  else:
    return report.longreprtext

def paramsForTest (item):
    paramKeysObj = None
    try:
      item.get_marker('parametrize')
    except AttributeError:
      # No get_marker in pytest 4
      pass
    if (paramKeysObj is None):
      try:
        item.get_closest_marker('parametrize')
      except AttributeError:
        # No get_closest_marker in pytest 3
        pass
    if (paramKeysObj):
        index = 0
        paramKeys = []
        while (index < len(paramKeysObj.args)):
            keys = paramKeysObj.args[index]
            keys = keys.split(",")
            for key in keys:
                paramKeys.append(key)
            index = index + 2
        params = {}
        values = item.name.split('[')
        if len(values) > 1:
            values = values[1]
            values = values[:-1] # removes ']'
            valuesSplit = values.split("-") # values now separated
            if len(valuesSplit) > len(paramKeys):
                params["[" + "-".join(paramKeys) + "]"] = "[" + values + "]"
            else:
                for key in paramKeys:
                    if (len(valuesSplit) > 0):
                        params[key] = valuesSplit.pop(0)
            return params
        else:
            return None
    else:
        return None

def filesForTest (suite, name):
  global filespath
  if (filespath is None):
    return
  files = []
  if (suite is None):
    suite = ''
  path = os.path.join(filespath, suite, name)
  if os.path.isdir(path):
    for dirpath, dirnames, filenames in os.walk(path):
        for file in filenames:
          if file != '.DS_Store': # Exclude os files
            files.append(os.path.join(path, file))
  return files

def pytest_runtest_setup(item):
  global disabled
  if (disabled == True):
    return
  startTimes[item.nodeid] = int(round(time.time() * 1000))

# A pytest hook, called by pytest automatically - used to extract test case data and append it to the data global variable defined above.
def pytest_runtest_protocol(item, nextitem):
  global disabled
  if (disabled == True):
    return
  global data
  reports = runtestprotocol(item, nextitem=nextitem)
  for report in reports:
    if report.when == 'call':
      name = item.name
      suite = None
      try:
        suite = item.get_marker('suite')
        if (suite):
          suite = suite.args[0] #extract val from marker
      except AttributeError:
        # no get_marker if pytest 4
        pass
      if (suite is None):
        try:
          suite = item.get_closest_marker('suite')
          if (suite):
            suite = suite.args[0] #extract val from marker
        except AttributeError:
          # no get_closest_marker in pytest 3
          pass
      if (suite is None):
        global nosuites
        if (nosuites == False):
          suite = str(item.parent.name)
          suite = suite.rpartition("/")[2]
          suite = suite.rpartition(".py")[0]
      testcase = {
      'name': name, 
      'result': tesultsFriendlyResult(report.outcome),
      'start': startTimes[item.nodeid],
      'end': int(round(time.time() * 1000)),
      'reason': reasonForFailure(report)
      }
      if (suite):
        testcase['suite'] = suite
      files = filesForTest(suite, name)
      if (files):
        if len(files) > 0:
          testcase['files'] = files
      params = paramsForTest(item)
      if (params):
        testcase['params'] = params
        testname = item.name.split('[')
        if len(testname) > 1:
          testcase['name'] = testname[0]
      paramDesc = None
      try:
        paramDesc = item.get_marker('description')
      except AttributeError:
        # no get_marker if pytest 4
        pass
      if (paramDesc is None):
        try:
          paramDesc = item.get_closest_marker('description')
        except AttributeError:
          # no get_closest_marker in pytest 3
          pass

      if (paramDesc):
        testcase['desc'] = paramDesc.args[0]
      data['results']['cases'].append(testcase)

      try:
        markers = item.iter_markers()
        for marker in markers:
          if (marker.name == 'description' or marker.name == 'desc'):
            testcase['desc'] = marker.args[0]
          elif (marker.name == 'parametrize' or marker.name == 'filterwarnings' or marker.name == 'skip' or marker.name == 'skipif' or marker.name == 'usefixtures' or marker.name == 'xfail' or marker.name == 'suite'):
            pass
          else:
            testcase['_' + marker.name] = marker.args[0]
      except AttributeError:
        pass  

  return True
# A pytest hook, called by pytest automatically - used to upload test results to tesults.
def pytest_unconfigure (config):
  global disabled
  if (disabled == True):
    return
  global data
  global buildcase
  if (buildcase):
    buildfiles = filesForTest(buildcase['suite'], buildcase['name'])
    if (buildfiles):
      if len(buildfiles) > 0:
        buildcase['files'] = buildfiles
    data['results']['cases'].append(buildcase)

  print ('Tesults results uploading...')
  if len(data['results']['cases']) > 0:
    #print ('data: ' + str(data))
    ret = tesults.results(data)
    print ('success: ' + str(ret['success']))
    print ('message: ' + str(ret['message']))
    print ('warnings: ' + str(ret['warnings']))
    print ('errors: ' + str(ret['errors']))
  else:
    print ('No test results.')
