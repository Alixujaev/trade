"""acquisition/akinda: Akinda B2B API v1 /compliance screening -> proposed Sharia eligibility-registry rows.

Owner provider decision D13-A (docs/shariah/AKINDA_PROVIDER_DECISION.md). Network access happens only in
`client.py`, only through `sync.py`, and only for an explicit ticker list. Nothing here places orders or edits
config/sharia_eligibility.csv; the ORB runner keeps reading the registry through screening/eligibility.py.
"""
