#!/bin/sh
pip install --quiet --no-warn-script-location pip-audit
exec pip-audit -f columns --skip-editable --ignore-vuln PYSEC-2025-49
