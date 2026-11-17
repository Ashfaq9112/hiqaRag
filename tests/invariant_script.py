from ingestion.models import ParsedReport

from collections import Counter

summary = {}

with open("data/parsed/reports.jsonl", encoding="utf-8") as f:
    for line in f:
        report = ParsedReport.model_validate_json(line)
        
        if report.compliance_plan is None: 
            continue
        resp_keys = [(responses.series, responses.regulation_number) for responses in report.compliance_plan.responses ]
        items_keys = [(item.series, item.regulation_number) for item in report.compliance_plan.items]
        
        missing = set(items_keys) - set(resp_keys)
        dedup_keys = [k  for k,n in Counter(resp_keys).items() if n>1]
        if len(missing)>0 or len(dedup_keys) >0:
            summary[report.source_file] = {"missing": list(missing),"dups": dedup_keys}
    


print(summary)


    