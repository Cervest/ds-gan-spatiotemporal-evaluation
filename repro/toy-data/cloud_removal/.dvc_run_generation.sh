dvc run -v -f -n generate_toy_cloud_removal_dataset \
-d run_toy_generation.py \
-d run_toy_derivation.py \
-d src/toygeneration/config/cloud_removal/optical/generation_latent_optical.yaml \
-d src/toygeneration/config/cloud_removal/optical/derivation_clean_optical.yaml \
-d src/toygeneration/config/cloud_removal/optical/derivation_clouded_optical.yaml \
-d src/toygeneration/config/cloud_removal/sar/generation_latent_sar.yaml \
-d src/toygeneration/config/cloud_removal/sar/derivation_sar.yaml \
-d data/ts/Multivariate_ts/RacketSports/RacketSports_TRAIN.ts \
-d data/ts/Multivariate_ts/RacketSports/RacketSports_TEST.ts \
-d data/ts/Multivariate_ts/Epilepsy/Epilepsy_TRAIN.ts \
-d data/ts/Multivariate_ts/Epilepsy/Epilepsy_TEST.ts \
-o data/toy/cloud_removal/ \
"source repro/toy-data/cloud_removal/generate_toy_cloud_removal_dataset.sh"
