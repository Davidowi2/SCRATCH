import sys
sys.path.insert(0, r'C:\Users\Legacy\Documents\SCRATCH\research')

from data.validate_data import audit

verdict = audit(
    r'C:\Users\Legacy\Documents\SCRATCH\tmp_oos_bounded_audit.log',
    r'C:\Users\Legacy\Documents\SCRATCH\tmp_oos_bounded',
    r'C:\Users\Legacy\Documents\SCRATCH\tmp_oos_bounded_clean.csv'
)
print(f'VERDICT: {verdict}')
