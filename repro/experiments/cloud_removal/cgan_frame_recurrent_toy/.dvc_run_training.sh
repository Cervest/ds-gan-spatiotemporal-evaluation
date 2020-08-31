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
CONFIG=src/rsgan/config/cloud_removal/cgan_frame_recurrent_toy.yaml
EXPERIMENT=src/rsgan/experiments/cloud_removal/cgan_frame_recurrent_toy_cloud_removal.py
DATASET=data/toy/cloud_removal
ROOT=data/experiments_outputs/cgan_frame_recurrent_toy_cloud_removal


# Run dvc pipeline on specified device
for SEED in 17 37 43 73 101 ;
do
  NAME=seed_$SEED
  TRAIN_DIR=$ROOT/$NAME/run
  dvc run -v -f -n train_cgan_frame_recurrent_toy_cloud_removal_$NAME \
  -d $CONFIG \
  -d $EXPERIMENT \
  -d $DATASET \
  -o $TRAIN_DIR \
  "python run_training.py --cfg=$CONFIG --o=$ROOT --device=$DEVICE --experiment_name=$NAME --seed=$SEED"
done
