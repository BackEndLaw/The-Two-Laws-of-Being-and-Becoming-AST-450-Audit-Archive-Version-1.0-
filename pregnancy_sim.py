#!/usr/bin/env python3
"""
Simple pregnancy Gate model.
Save as pregnancy_sim.py and run: python3 pregnancy_sim.py
"""

import numpy as np

def mutual_info_discrete(x, y, bins=10):
    # discretize and compute MI in bits using histogram estimation
    x_edges = np.histogram_bin_edges(x, bins=bins)
    y_edges = np.histogram_bin_edges(y, bins=bins)
    x_bins = np.digitize(x, x_edges) - 1
    y_bins = np.digitize(y, y_edges) - 1
    # clip to valid range
    x_bins = np.clip(x_bins, 0, bins-1)
    y_bins = np.clip(y_bins, 0, bins-1)
    pxy, _, _ = np.histogram2d(x_bins, y_bins, bins=(bins, bins))
    total = pxy.sum()
    if total == 0:
        return 0.0
    pxy = pxy / total
    px = pxy.sum(axis=1)
    py = pxy.sum(axis=0)
    mi = 0.0
    for i in range(bins):
        for j in range(bins):
            if pxy[i, j] > 0 and px[i] > 0 and py[j] > 0:
                mi += pxy[i, j] * np.log(pxy[i, j] / (px[i] * py[j]))
    # convert nats -> bits
    return mi / np.log(2.0)

def simulate_one(rng, params):
    # sample p features
    genotype = rng.uniform(params['genotype_min'], 1.0)    # [genotype_min,1]
    epigenetic = np.clip(rng.normal(0.5, 0.15), 0.0, 1.0) # marker in [0,1]
    maternal_health = rng.uniform(params['maternal_min'], 1.0)
    p = np.array([genotype, epigenetic, maternal_health])

    # dynamics
    dev = params['dev0']
    for t in range(params['gest_steps']):
        # deterministic growth proportional to genotype and maternal health
        growth = params['base_rate'] * genotype * maternal_health
        # prenatal support (Boat type: increases growth)
        growth += params['prenatal_boost'] * maternal_health
        dev += growth
        # stochastic insult
        if rng.random() < params['insult_prob']:
            # severity scaled inversely by maternal_health
            severity = rng.exponential(scale=0.1) * (1.0 - 0.5 * maternal_health)
            dev -= severity
        # clamp
        dev = max(0.0, min(1.5, dev))  # allow above 1 to represent robust development

    # birth outcome
    survive = False
    if dev >= params['threshold']:
        survive = True
    else:
        # neonatal rescue probability depends on neonatal_care_effectiveness and dev/threshold
        rescue_chance = params['neonatal_effect'] * (dev / params['threshold'])
        if rng.random() < rescue_chance:
            survive = True
    return {'p': p, 'dev': dev, 'survive': int(survive)}

def run_simulation(seed=0, N=10000, params=None):
    if params is None:
        params = default_params()
    rng = np.random.default_rng(seed)
    results = [simulate_one(rng, params) for _ in range(N)]
    p_mat = np.array([r['p'] for r in results])
    devs = np.array([r['dev'] for r in results])
    survives = np.array([r['survive'] for r in results])
    stats = {
        'P_survive': survives.mean(),
        'avg_dev': devs.mean(),
        'mi_genotype': mutual_info_discrete(p_mat[:,0], survives, bins=12),
        'mi_epigenetic': mutual_info_discrete(p_mat[:,1], survives, bins=12),
        'mi_maternal': mutual_info_discrete(p_mat[:,2], survives, bins=12),
        'N': N
    }
    return stats, p_mat, devs, survives

def default_params():
    return {
        'gest_steps': 40,       # gestational time steps
        'base_rate': 0.02,      # base per-step developmental increment
        'dev0': 0.05,           # initial development
        'threshold': 0.8,       # required dev to survive without rescue
        'insult_prob': 0.03,    # per-step chance of an insult
        'prenatal_boost': 0.0,  # extra growth from prenatal care (Boat)
        'neonatal_effect': 0.5, # effectiveness of neonatal care (Boat) in [0,1]
        'genotype_min': 0.5,    # min genotype quality sampled
        'maternal_min': 0.4     # min maternal health
    }

def compare_scenarios():
    params = default_params()
    scenarios = [
        ('Baseline', dict(params)),
        ('Prenatal support', dict(params, prenatal_boost=0.01)),
        ('Stronger prenatal', dict(params, prenatal_boost=0.02)),
        ('Better neonatal care', dict(params, neonatal_effect=0.9)),
        ('Both support', dict(params, prenatal_boost=0.01, neonatal_effect=0.9))
    ]
    print(f"{'Scenario':20s} {'P_survive':>9s} {'avg_dev':>9s} {'MI_gen':>8s} {'MI_epi':>8s} {'MI_mat':>8s}")
    for name, p in scenarios:
        stats, _, _, _ = run_simulation(seed=123, N=10000, params=p)
        print(f"{name:20s} {stats['P_survive']:9.4f} {stats['avg_dev']:9.4f} {stats['mi_genotype']:8.3f} {stats['mi_epigenetic']:8.3f} {stats['mi_maternal']:8.3f}")

if __name__ == '__main__':
    compare_scenarios()
