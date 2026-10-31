"""Explainable demonstration model. No real-world calibration is claimed."""
import math
import random
from functools import lru_cache
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import precision_score, recall_score, f1_score, confusion_matrix
from sklearn.model_selection import train_test_split

FEATURES = ['rainfall_24h', 'rainfall_72h', 'soil_moisture', 'slope', 'past_incidents', 'vegetation_loss']
LIMITS = [(0, 600), (0, 1800), (0, 100), (0, 80), (0, 50), (0, 100)]

def baseline(v):
    parts = [min(v[0]/250, 1)*30, min(v[1]/600, 1)*15,
             min(v[2]/100, 1)*20, min(v[3]/60, 1)*20,
             min(v[4]/10, 1)*10, min(v[5]/60, 1)*5]
    return sum(parts), parts

@lru_cache(maxsize=1)
def model():
    rng = random.Random(26001)
    x, y = [], []
    for _ in range(2400):
        r = rng.uniform(0, 400)
        v = [r, r + rng.uniform(0, 700), rng.uniform(15, 100), rng.uniform(3, 65), rng.randrange(15), rng.uniform(0, 80)]
        score, _ = baseline(v)
        # Synthetic expert-rule labels with noise: an engineering benchmark only.
        probability = 1 / (1 + math.exp(-(score-61)/8))
        x.append(v); y.append(int(rng.random() < probability))
    xt, xv, yt, yv = train_test_split(x, y, test_size=.25, stratify=y, random_state=26)
    rf = RandomForestClassifier(n_estimators=80, max_depth=8, min_samples_leaf=8, random_state=26, n_jobs=1)
    rf.fit(xt, yt)
    pred = rf.predict(xv)
    metrics = dict(precision=round(precision_score(yv, pred), 3), recall=round(recall_score(yv, pred), 3),
                   f1=round(f1_score(yv, pred), 3), confusion_matrix=confusion_matrix(yv, pred).tolist(),
                   training_samples=len(xt), test_samples=len(xv), training_source='Synthetic rule-generated samples',
                   validated_for_operations=False, version='rf-demo-1.0',
                   importance=dict(zip(FEATURES, [round(float(z), 3) for z in rf.feature_importances_])))
    return rf, metrics

def predict(values):
    v = [float(values[k]) for k in FEATURES]
    if any(not math.isfinite(z) or z < lo or z > hi for z, (lo, hi) in zip(v, LIMITS)):
        raise ValueError('Input is outside the supported physical range')
    if v[1] < v[0]:
        raise ValueError('72-hour cumulative rainfall must be at least 24-hour rainfall')
    rules, parts = baseline(v)
    rf, _ = model()
    ml = float(rf.predict_proba([v])[0][1]) * 100
    score = round(.65 * rules + .35 * ml)
    level = 'Critical' if score >= 75 else 'High' if score >= 55 else 'Moderate' if score >= 35 else 'Low'
    action = {'Critical':'Prioritize immediate official verification; prepare access restrictions and community contact.',
              'High':'Assign a slope inspection and monitor the affected road corridor.',
              'Moderate':'Increase observation frequency and check drainage and recent reports.',
              'Low':'Continue routine monitoring; low score does not establish safety.'}[level]
    drivers = sorted([{'feature': k, 'value': v[i], 'contribution': round(parts[i], 1)} for i, k in enumerate(FEATURES)], key=lambda d:d['contribution'], reverse=True)
    return dict(score=score, level=level, rule_score=round(rules, 1), model_score=round(ml, 1),
                drivers=drivers, action=action, method='65% transparent rules + 35% Random Forest',
                model_version='rf-demo-1.0', calibrated_probability=False,
                limitation='Demonstration risk index, not an event probability or an official warning.')
