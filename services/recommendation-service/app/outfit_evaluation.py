"""Offline evaluation of outfit ranking against a transparent rule baseline."""
from __future__ import annotations
import argparse, json, math
from collections import Counter
from pathlib import Path

def _strings(values, field, required=False):
    if values is None and not required: return set()
    if not isinstance(values,list) or any(not isinstance(x,str) or not x.strip() for x in values):
        raise ValueError(f"{field} must be a list of non-empty strings")
    return {" ".join(x.casefold().split()) for x in values}

def _tags(candidate):
    return _strings(candidate.get("tags"),"tags") | _strings(candidate.get("categories"),"categories")

def _items(candidate):
    return _strings(candidate.get("item_ids"),"item_ids",True)

def _validate(row):
    for key in ("case_id","user_key","reviewed_at"):
        if not isinstance(row.get(key),str) or not row[key].strip(): raise ValueError(f"{key} is required")
    if row.get("schema_version")!="1.0" or row.get("split") not in {"train","validation","test"}:
        raise ValueError("schema_version must be 1.0 and split must be train, validation, or test")
    _strings(row.get("preferred_tags",[]),"preferred_tags"); _strings(row.get("excluded_tags",[]),"excluded_tags")
    pool=row.get("candidate_pool")
    if not isinstance(pool,list) or not pool: raise ValueError("candidate_pool must be non-empty")
    seen=set()
    for c in pool:
        if not isinstance(c,dict): raise ValueError("candidate must be an object")
        cid=c.get("candidate_id")
        if not isinstance(cid,str) or not cid.strip() or cid in seen: raise ValueError("candidate_id must be unique")
        seen.add(cid); _items(c); _strings(c.get("categories"),"categories",True); _strings(c.get("tags"),"tags",True)
        score=c.get("model_score")
        if not isinstance(score,(int,float)) or isinstance(score,bool) or not math.isfinite(score): raise ValueError("model_score must be finite")
        reviews=c.get("human_reviews")
        if not isinstance(reviews,list) or len(reviews)<2: raise ValueError("each candidate requires at least two independent human_reviews")
        reviewers=set()
        for review in reviews:
            if not isinstance(review,dict) or not isinstance(review.get("reviewer_key"),str) or not review["reviewer_key"].strip():
                raise ValueError("each human review requires a pseudonymous reviewer_key")
            reviewer=review["reviewer_key"]
            if reviewer in reviewers: raise ValueError("reviewer_key must be unique per candidate")
            reviewers.add(reviewer)
            rating=review.get("relevance")
            if not isinstance(rating,int) or isinstance(rating,bool) or rating not in range(1,6):
                raise ValueError("human review relevance must be an integer 1-5")
        for flag in ("shown","user_edited","user_rejected"):
            if not isinstance(c.get(flag,False),bool): raise ValueError(f"{flag} must be boolean")
        if (c.get("user_edited") or c.get("user_rejected")) and not c.get("shown"):
            raise ValueError("user edit/rejection requires a shown impression")
        if c.get("user_rejected") and (not isinstance(c.get("rejection_key"),str) or not c["rejection_key"].strip()):
            raise ValueError("rejection_key required for rejected impressions")

def _human_rating(candidate):
    reviews=candidate["human_reviews"]
    return sum(r["relevance"] for r in reviews)/len(reviews)

def _baseline_key(c,preferred,excluded):
    tags=_tags(c)
    return (bool(tags&excluded),-len(tags&preferred),-len(_strings(c["categories"],"categories")),-min(len(_items(c)),4),str(c["candidate_id"]))

def _rank(row,method):
    pool=row["candidate_pool"]
    if method=="candidate_model": return sorted(pool,key=lambda c:(-float(c["model_score"]),str(c["candidate_id"])))
    p=_strings(row.get("preferred_tags",[]),"preferred_tags"); e=_strings(row.get("excluded_tags",[]),"excluded_tags")
    return sorted(pool,key=lambda c:_baseline_key(c,p,e))

def _metrics(rows,method,k):
    chosen=[]; ratings=[]; distances=[]; violations=0
    for row in rows:
        top=_rank(row,method)[:k]; chosen.extend(top); ratings.extend(_human_rating(c) for c in top)
        excluded=_strings(row.get("excluded_tags",[]),"excluded_tags")
        violations+=sum(bool(_tags(c)&excluded) for c in top)
        for i,a in enumerate(top):
            ai=_items(a)
            for b in top[i+1:]:
                bi=_items(b); union=ai|bi
                distances.append(1-len(ai&bi)/len(union) if union else 0.0)
    n=len(chosen)
    return {"outfit_count_at_k":n,"relevance_mean_at_k":round(sum(ratings)/n,6) if n else 0.0,
      "diversity_mean_pairwise_item_jaccard_distance_at_k":round(sum(distances)/len(distances),6) if distances else 0.0,
      "exclusion_violation_rate_at_k":round(violations/n,6) if n else 0.0}

def _outcomes(rows):
    shown=[(r,c) for r in rows for c in r["candidate_pool"] if c.get("shown")]
    rejected=[(r["user_key"],c["rejection_key"]) for r,c in shown if c.get("user_rejected")]
    counts=Counter(rejected); n=len(rejected)
    return {"shown_recommendation_count":len(shown),
      "user_edit_rate":round(sum(c.get("user_edited",False) for _,c in shown)/len(shown),6) if shown else 0.0,
      "user_rejection_count":n,
      "repeated_rejection_rate_among_rejections":round(sum(v for v in counts.values() if v>1)/n,6) if n else 0.0,
      "repeated_user_rejection_pairs":sum(v>1 for v in counts.values())}

def evaluate(rows,k=3):
    rows=list(rows)
    if k<1 or not rows: raise ValueError("k must be positive and dataset non-empty")
    cases=set(); participant_split={}
    for row in rows:
        _validate(row); key=(row["split"],row["case_id"])
        if key in cases: raise ValueError("case_id must be unique within split")
        cases.add(key)
        previous=participant_split.setdefault(row["user_key"],row["split"])
        if previous!=row["split"]: raise ValueError("participant leakage across dataset splits")
    report={"schema_version":"1.0","k":k,"case_count":len(rows),"split_metrics":{},
      "observed_user_outcomes":{},"paired_model_minus_baseline":{},
      "human_annotation":{"minimum_independent_reviewers_per_candidate":2,"candidate_relevance":"mean of independent blinded reviewer scores"}}
    for split in ("train","validation","test"):
        subset=[r for r in rows if r["split"]==split]
        if not subset: continue
        model=_metrics(subset,"candidate_model",k); baseline=_metrics(subset,"simple_baseline",k)
        report["split_metrics"][split]={"candidate_model":model,"simple_baseline":baseline}
        report["paired_model_minus_baseline"][split]={x:round(model[x]-baseline[x],6) for x in model if x!="outfit_count_at_k"}
        report["observed_user_outcomes"][split]=_outcomes(subset)
    return report

def main():
    parser=argparse.ArgumentParser(description="Evaluate outfit rankings against a rule-based baseline.")
    parser.add_argument("dataset"); parser.add_argument("--k",type=int,default=3); parser.add_argument("--output")
    args=parser.parse_args(); rows=[]
    with Path(args.dataset).open(encoding="utf-8") as stream:
        for n,line in enumerate(stream,1):
            if line.strip():
                try: rows.append(json.loads(line))
                except json.JSONDecodeError as exc: raise ValueError(f"invalid JSON line {n}") from exc
    rendered=json.dumps(evaluate(rows,args.k),indent=2,sort_keys=True)
    if args.output: Path(args.output).write_text(rendered+"\n",encoding="utf-8")
    print(rendered)
if __name__=="__main__": main()
