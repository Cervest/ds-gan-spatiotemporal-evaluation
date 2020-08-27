# Retrive device id
for i in "$@"
do
case $i in
    --device=*)
    DEVICE="${i#*=}"
    shift # past argument=value
    ;;
    *)
          # unknown option
    ;;
esac
done

# Define main path variables
CONFIG=src/rsgan/config/cloud_removal/cgan_upper_bound_toy.yaml
EXPERIMENT=src/rsgan/experiments/cloud_removal/cgan_toy_cloud_removal.py
DATASET=data/toy/cloud_removal
ROOT=data/experiments_outputs/cgan_upper_bound_toy
TRAIN_DIR=$ROOT/dvc_run/run/
TEST_DIR=$ROOT/dvc_run/eval/

# Run dvc pipeline on specified device
dvc run -v -n test_cgan_toy_upper_bound \
-d $CONFIG \
-d $EXPERIMENT \
-d $DATASET \
-d $TRAIN_DIR \
-o $TEST_DIR \
"python make_reference_classifier.py --cfg=$CONFIG --o=$TEST_DIR/reference_classifier/classifier.pickle \
  && python run_testing.py --cfg=$CONFIG --o=$ROOT --device=$DEVICE"
