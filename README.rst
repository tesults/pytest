==============
pytest-tesults
==============

Tesults plugin for pytest

------------


Description
------------

Tesults is the new standard in automated test results consolidation, reporting, analysis, failure tracking, manual test reporting and test case management.

Use pytest-tesults to automatically integrate with Tesults.

For complete details visit:

https://www.tesults.com/docs/pytest


Requirements
------------

The Tesults Python library is required. Install using pip from PyPI:

$ pip install tesults


Installation
------------

Install pytest-tesults using pip from PyPI:

$ pip install pytest-tesults


Usage
-----

Visit https://www.tesults.com/docs/pytest for documentation.


GitHub Actions
--------------

``pytest-tesults`` can produce a local results file for the Tesults Test
Automation Reporting action. No Tesults target token is required for this
mode.

Install ``pytest-tesults>=1.9.0``, add the action before the test step, and run
pytest as usual:

.. code-block:: yaml

   - uses: tesults/test-automation-reporting@v1
   - run: pytest

The action sets ``TESULTS_OUTPUT_FILE`` automatically. If both that environment
variable and ``--tesults-target`` are present, the reporter writes the local
results file and uploads the same run to Tesults.


License
-------

Distributed under the terms of the MIT license, "pytest-tesults" is free and open source software


Issues
------

If you encounter any problems, please contact help@tesults.com or visit https://www.tesults.com/contact
