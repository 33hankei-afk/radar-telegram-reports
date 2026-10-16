from pathlib import Path
import json,sys
from global_position_contract import validate
for path in sys.argv[1:]:
 obj=validate(json.loads(Path(path).read_text(encoding='utf-8')))
 print(str(path)+': valid '+obj['producer']+' '+obj['date_kst'])
