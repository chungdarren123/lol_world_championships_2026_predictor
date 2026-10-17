# Project purpose and agreed constraints

- This is a beginner machine-learning learning project. Teach concepts, explain alternatives and their pros and cons, and connect implementation choices to the learning objective.
- Discuss major architecture and modeling decisions with the user before implementing them. Prefer small, understandable increments with inspectable intermediate results.
- Use regional and international professional tournament data only. Exclude solo queue and ranked-player API data.
- The first forecast must use only information available before the first game of Worlds 2026, including Play-Ins. Verify the precise cutoff before building the dataset.
- Exclude Worlds 2026 results and derived information from this initial forecast's training, feature construction, tuning, and calibration. Keep any eventual retrospective evaluation separate.
- Distinguish a historical match date from when its data became available. Disclose uncertainty if reconstructing an authentic pre-tournament snapshot from subsequently downloaded or corrected records.
- Approved architecture: modular Python application, Elo baseline, logistic regression, and a separate series/tournament simulator. Do not introduce notebooks as the implementation interface.
- Use only the 2026 competitive season's regional and international professional tournament data before the Worlds cutoff. Audit coverage; do not claim complete coverage without evidence. Track midseason roster changes.
- Initial scope: game-win probabilities, then series results, then tournament outcomes. Champion forecasting is deferred.
- The user is comfortable with Python; teach machine-learning concepts without assuming they need basic Python instruction.
- Work through GitHub repository chungdarren123/lol_world_championships_2026_predictor. Begin with terminal workflows; eventual output is a deployed, hosted visualization. Hosting platform and frontend framework are not yet selected.
