"""Constrained, non-centred hierarchical Bradley-Terry in PyMC.

Numeric dependencies are imported only by model commands; audits stay stdlib-only.
"""


def zero_sum_basis(size):
    """Orthonormal Helmert contrasts: full rank on the sum-zero subspace."""
    import numpy as np
    basis = np.zeros((size, max(0, size - 1)))
    for j in range(size - 1):
        denom = ((j + 1) * (j + 2)) ** 0.5
        basis[:j + 1, j] = 1 / denom
        basis[j + 1, j] = -(j + 1) / denom
    return basis


def design_matrices(data):
    import numpy as np
    n, r = len(data["entities"]), len(data["regions"])
    region_basis = zero_sum_basis(r)
    # Preserve the stated marginal SD after applying the zero-sum constraint.
    if r > 1:
        region_basis *= (r / (r - 1)) ** 0.5
    team_basis = np.zeros((n, n - r))
    offset = 0
    for region in range(r):
        members = [i for i, label in enumerate(data["region_index"]) if label == region]
        size = len(members)
        if size > 1:
            block = zero_sum_basis(size) * (size / (size - 1)) ** 0.5
            team_basis[np.ix_(members, range(offset, offset + size - 1))] = block
            offset += size - 1
    return region_basis, team_basis


def build_model(data, config):
    import numpy as np
    import pymc as pm
    import pytensor.tensor as pt
    if config["region_scale_prior"] <= 0 or config["team_scale_prior"] <= 0:
        raise ValueError("Prior scales must be positive.")
    rb, tb = design_matrices(data)
    pairs = data["pairs"]
    coords = {"region": data["regions"], "entity": list(range(len(data["entities"]))),
              "pair": list(range(len(pairs)))}
    with pm.Model(coords=coords) as model:
        # The singleton cases have exactly zero effect and no redundant scale.
        if rb.shape[1]:
            region_sd = pm.HalfNormal("region_sd", sigma=config["region_scale_prior"])
            z_region = pm.Normal("z_region", 0, 1, shape=rb.shape[1])
            regional = region_sd * pt.dot(rb, z_region)
        else:
            regional = pt.zeros(len(data["regions"]))
        region_effect = pm.Deterministic("region_effect", regional, dims="region")
        if tb.shape[1]:
            team_sd = pm.HalfNormal("team_sd", sigma=config["team_scale_prior"])
            z_team = pm.Normal("z_team", 0, 1, shape=tb.shape[1])
            deviation = team_sd * pt.dot(tb, z_team)
        else:
            deviation = pt.zeros(len(data["entities"]))
        team_effect = pm.Deterministic("team_effect", deviation, dims="entity")
        strength = pm.Deterministic("strength", region_effect[np.array(data["region_index"])] + team_effect,
                                    dims="entity")
        a, b = (np.array([p[key] for p in pairs], dtype=int) for key in ("a", "b"))
        pm.Binomial("wins", n=np.array([p["games"] for p in pairs]),
                    logit_p=strength[a] - strength[b],
                    observed=np.array([p["wins_a"] for p in pairs]), dims="pair")
    return model


def fit_model(data, config):
    import os
    from pathlib import Path
    cache = Path("artifacts/runtime_cache").resolve()
    os.environ.setdefault("MPLCONFIGDIR", str(cache / "matplotlib"))
    # PyTensor parses backslashes in flags as escapes; use portable slashes.
    flags = "compiledir=" + (cache / "pytensor").as_posix()
    if os.name == "nt":
        flags = "cxx=," + flags
    os.environ.setdefault("PYTENSOR_FLAGS", flags)
    import pymc as pm
    model = build_model(data, config)
    with model:
        prior = pm.sample_prior_predictive(samples=config["prior_draws"], random_seed=config["seed"])
        posterior = pm.sample(draws=config["draws"], tune=config["tune"], chains=config["chains"],
                              cores=1, target_accept=config["target_accept"],
                              random_seed=config["seed"], progressbar=False,
                              nuts_sampler="numpyro",
                              nuts_sampler_kwargs={"chain_method": "vectorized", "nuts_kwargs": {
                                  "max_tree_depth": config["max_tree_depth"]}},
                              idata_kwargs={"log_likelihood": False})
    return posterior, prior


def matchup_draws(strength_draws, team_a, team_b):
    """Complementary probabilities with each joint posterior draw preserved."""
    import numpy as np
    if team_a == team_b:
        raise ValueError("A team cannot play itself.")
    x = strength_draws[..., team_a] - strength_draws[..., team_b]
    return np.exp(-np.logaddexp(0, -x))
