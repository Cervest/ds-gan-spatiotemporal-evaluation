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
SEEDS=(17 37 43 73 101)
CHKPTS=("seed_17/checkpoints/epoch=42.ckpt"
        "seed_37/checkpoints/epoch=62.ckpt"
        "seed_43/checkpoints/epoch=60.ckpt"
        "seed_73/checkpoints/epoch=63.ckpt"
        "seed_101/checkpoints/epoch=61.ckpt")


# Run dvc pipeline on specified device
for (( i=0; i<${#SEEDS[*]}; ++i));
do
  NAME=seed_${SEEDS[$i]}
  CHKPT=$ROOT/${CHKPTS[$i]}
  TRAIN_DIR=$ROOT/$NAME/run
  TEST_DIR=$ROOT/$NAME/eval
  CLASSIFIER=$TEST_DIR/reference_classifier/classifier.pickle
  dvc run -v -f -n test_cgan_toy_upper_bound_$NAME \
  -d $CONFIG \
  -d $EXPERIMENT \
  -d $DATASET \
  -d $TRAIN_DIR \
  -d $CHKPT \
  -o $TEST_DIR \
  "python make_reference_classifier.py --cfg=$CONFIG --o=$CLASSIFIER \
    && python run_testing.py --cfg=$CONFIG --o=$ROOT --device=$DEVICE --chkpt=$CHKPT --classifier=$CLASSIFIER"
done
