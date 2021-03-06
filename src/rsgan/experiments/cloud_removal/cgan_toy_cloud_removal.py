import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader

from src.rsgan import build_model, build_dataset
from src.rsgan.experiments import EXPERIMENTS
from src.rsgan.experiments.experiment import ToyImageTranslationExperiment
from src.rsgan.experiments.utils import collate
from src.utils import load_pickle


@EXPERIMENTS.register('cgan_toy_cloud_removal')
class cGANToyCloudRemoval(ToyImageTranslationExperiment):
    """Setup to train and evaluate conditional GANs at cloud removal on toy dataset
        using clouded optical-like image and SAR-like toy image

                             +-----------+
       clouded_optical ----->+           +
                             | Generator |---> predicted_clean_optical
                   SAR ----->+           +
                             +-----------+

    We investigate deep generative models ability to extrapolate clouded optical
    imagery reflectance into structural spatial information provided by SAR imagery
    which is unaffected by clouds and

    Experimental setup based on :
    ```
    @INPROCEEDINGS{8519215,
      author={C. {Grohnfeldt} and M. {Schmitt} and X. {Zhu}},
      booktitle={IGARSS 2018 - 2018 IEEE International Geoscience and Remote Sensing Symposium},
      title={A Conditional Generative Adversarial Network to Fuse Sar And Multispectral Optical Data For Cloud Removal From Sentinel-2 Images},
      year={2018},
    }
    ```

    Args:
        generator (nn.Module)
        discriminator (nn.Module)
        dataset (ToyCloudRemovalDataset)
        split (list[float]): dataset split ratios in [0, 1] as [train, val]
            or [train, val, test]
        l1_weight (float): weight of l1 regularization term
        dataloader_kwargs (dict): parameters of dataloaders
        optimizer_kwargs (dict): parameters of optimizer defined in LightningModule.configure_optimizers
        lr_scheduler_kwargs (dict): paramters of lr scheduler defined in LightningModule.configure_optimizers
        reference_classifier (sklearn.BaseEstimator): reference pixelwise timeserie classifier for evaluation
        seed (int): random seed (default: None)
    """
    def __init__(self, generator, discriminator, dataset, split, dataloader_kwargs,
                 optimizer_kwargs, lr_scheduler_kwargs=None, l1_weight=None,
                 reference_classifier=None, seed=None):
        super().__init__(model=generator,
                         dataset=dataset,
                         split=split,
                         dataloader_kwargs=dataloader_kwargs,
                         optimizer_kwargs=optimizer_kwargs,
                         lr_scheduler_kwargs=lr_scheduler_kwargs,
                         criterion=nn.BCELoss(),
                         reference_classifier=reference_classifier,
                         seed=seed)
        self.l1_weight = l1_weight
        self.discriminator = discriminator

    def forward(self, x):
        return self.generator(x)

    def train_dataloader(self):
        """Implements LightningModule train loader building method
        """
        # Make dataloader of (source, target) - no annotation needed
        self.train_set.dataset.use_annotations = False

        # Subsample from dataset to avoid having too many similar views from same time serie
        train_set = self._regular_subsample(dataset=self.train_set,
                                            subsampling_rate=5)

        # Instantiate loader
        train_loader_kwargs = self.dataloader_kwargs.copy()
        train_loader_kwargs.update({'dataset': train_set,
                                    'shuffle': True,
                                    'collate_fn': collate.stack_input_frames})
        loader = DataLoader(**train_loader_kwargs)
        return loader

    def val_dataloader(self):
        """Implements LightningModule validation loader building method
        """
        # Make dataloader of (source, target) - no annotation needed
        self.val_set.dataset.use_annotations = False

        # Instantiate loader
        val_loader_kwargs = self.dataloader_kwargs.copy()
        val_loader_kwargs.update({'dataset': self.val_set,
                                  'collate_fn': collate.stack_input_frames})
        loader = DataLoader(**val_loader_kwargs)
        return loader

    def test_dataloader(self):
        """Implements LightningModule test loader building method
        """
        # Make dataloader of (source, target, annotation)
        self.test_set.dataset.use_annotations = True

        # Instantiate loader with batch size = horizon s.t. full time series are loaded
        test_loader_kwargs = self.dataloader_kwargs.copy()
        test_loader_kwargs.update({'dataset': self.test_set,
                                   'batch_size': self.test_set.dataset.horizon,
                                   'collate_fn': collate.stack_annotated_input_frames})
        loader = DataLoader(**test_loader_kwargs)
        return loader

    def configure_optimizers(self):
        """Implements LightningModule optimizer and learning rate scheduler
        building method
        """
        # Separate optimizers for generator and discriminator
        gen_optimizer = torch.optim.Adam(self.parameters(), **self.optimizer_kwargs['generator'])
        disc_optimizer = torch.optim.Adam(self.discriminator.parameters(), **self.optimizer_kwargs['discriminator'])

        # Separate learning rate schedulers
        gen_lr_scheduler = torch.optim.lr_scheduler.ExponentialLR(gen_optimizer,
                                                                  **self.lr_scheduler_kwargs['generator'])
        disc_lr_scheduler = torch.optim.lr_scheduler.ExponentialLR(disc_optimizer,
                                                                   **self.lr_scheduler_kwargs['discriminator'])

        # Make lightning output dictionnary fashion
        gen_optimizer_dict = {'optimizer': gen_optimizer, 'scheduler': gen_lr_scheduler, 'frequency': 1}
        disc_optimizer_dict = {'optimizer': disc_optimizer, 'scheduler': disc_lr_scheduler, 'frequency': 2}
        return gen_optimizer_dict, disc_optimizer_dict

    def _step_generator(self, source, target):
        """Runs generator forward pass and loss computation

        Args:
            source (torch.Tensor): (batch_size, C, H, W) tensor
            target (torch.Tensor): (batch_size, C, H, W) tensor

        Returns:
            type: dict
        """
        # Forward pass on source domain data
        estimated_target = self(source)
        output_fake_sample = self.discriminator(estimated_target, source)

        # Compute generator fooling power
        target_real_sample = torch.ones_like(output_fake_sample)
        gen_loss = self.criterion(output_fake_sample, target_real_sample)

        # Compute L1 regularization term
        mae = F.smooth_l1_loss(estimated_target, target)
        return gen_loss, mae

    def _step_discriminator(self, source, target):
        """Runs discriminator forward pass, loss computation and classification
        metrics computation

        Args:
            source (torch.Tensor): (batch_size, C, H, W) tensor
            target (torch.Tensor): (batch_size, C, H, W) tensor

        Returns:
            type: dict
        """
        # Forward pass on target domain data
        output_real_sample = self.discriminator(target, source)

        # Compute discriminative power on real samples
        target_real_sample = torch.ones_like(output_real_sample)
        loss_real_sample = self.criterion(output_real_sample, target_real_sample)

        # Generate fake sample + forward pass, we detach fake samples to not backprop though generator
        estimated_target = self.model(source)
        output_fake_sample = self.discriminator(estimated_target.detach(), source)

        # Compute discriminative power on fake samples
        target_fake_sample = torch.zeros_like(output_fake_sample)
        loss_fake_sample = self.criterion(output_fake_sample, target_fake_sample)
        disc_loss = loss_real_sample + loss_fake_sample

        # Compute classification training metrics
        fooling_rate, precision, recall = self._compute_classification_metrics(output_real_sample, output_fake_sample)
        return disc_loss, fooling_rate, precision, recall

    def training_step(self, batch, batch_idx, optimizer_idx):
        """Implements LightningModule training logic

        Args:
            batch (tuple[torch.Tensor]): source, target pairs batch
            batch_idx (int)
            optimizer_idx (int): {0: gen_optimizer, 1: disc_optimizer}

        Returns:
            type: dict
        """
        # Unfold batch
        source, target = batch

        # Run either generator or discriminator training step
        if optimizer_idx == 0:
            gen_loss, mae = self._step_generator(source, target)
            logs = {'Loss/train_generator': gen_loss,
                    'Metric/train_mae': mae}
            loss = gen_loss + self.l1_weight * mae

        if optimizer_idx == 1:
            disc_loss, fooling_rate, precision, recall = self._step_discriminator(source, target)
            logs = {'Loss/train_discriminator': disc_loss,
                    'Metric/train_fooling_rate': fooling_rate,
                    'Metric/train_precision': precision,
                    'Metric/train_recall': recall}
            loss = disc_loss

        # Make lightning fashion output dictionnary
        output = {'loss': loss,
                  'progress_bar': logs,
                  'log': logs}
        return output

    def on_epoch_end(self):
        """Implements LightningModule end of epoch operations
        """
        # Compute generated samples out of logging images
        source, target = self.logger._logging_images
        with torch.no_grad():
            output = self(source)

        if self.current_epoch == 0:
            # Log input and groundtruth once only at first epoch
            self.logger.log_images(source[:, :3], tag='Source - Optical (fake RGB)', step=self.current_epoch)
            self.logger.log_images(source[:, -3:], tag='Source - SAR (fake RGB)', step=self.current_epoch)
            self.logger.log_images(target[:, :3], tag='Target - Optical (fake RGB)', step=self.current_epoch)

        # Log generated image at current epoch
        self.logger.log_images(output[:, :3], tag='Generated - Optical (fake RGB)', step=self.current_epoch)

    def validation_step(self, batch, batch_idx):
        """Implements LightningModule validation logic

        Args:
            batch (tuple[torch.Tensor]): source, target pairs batch
            batch_idx (int)

        Returns:
            type: dict
        """
        # Unfold batch
        source, target = batch

        # Store into logger images for visualization
        if not hasattr(self.logger, '_logging_images'):
            self.logger._logging_images = source[:8], target[:8]

        # Run forward pass on generator and discriminator
        gen_loss, mae = self._step_generator(source, target)
        disc_loss, fooling_rate, precision, recall = self._step_discriminator(source, target)

        # Encapsulate scores in torch tensor
        output = torch.Tensor([gen_loss, mae, disc_loss, fooling_rate, precision, recall])
        return output

    def validation_epoch_end(self, outputs):
        """LightningModule validation epoch end hook

        Args:
            outputs (list[torch.Tensor]): list of validation steps outputs

        Returns:
            type: dict
        """
        # Average loss and metrics
        outputs = torch.stack(outputs).mean(dim=0)
        gen_loss, mae, disc_loss, fooling_rate, precision, recall = outputs

        # Make tensorboard logs and return
        logs = {'Loss/val_generator': gen_loss.item(),
                'Loss/val_discriminator': disc_loss.item(),
                'Metric/val_mae': mae.item(),
                'Metric/val_fooling_rate': fooling_rate.item(),
                'Metric/val_precision': precision.item(),
                'Metric/val_recall': recall.item()}

        # Make lightning fashion output dictionnary - track discriminator max loss for validation
        output = {'val_loss': disc_loss,
                  'log': logs,
                  'progress_bar': logs}
        return output

    def test_step(self, batch, batch_idx):
        """Implements LightningModule testing logic

        Args:
            batch (tuple[torch.Tensor]): source, target pairs batch
            batch_idx (int)

        Returns:
            type: dict
        """
        # Unfold batch
        source, target, annotation = batch

        # Run generator forward pass
        generated_target = self(source)

        # Compute performance at downstream classification task
        iou_generated, iou_real = self._compute_legitimacy_at_task_score(self.reference_classifier,
                                                                         generated_target,
                                                                         target,
                                                                         annotation)

        # Compute IQA metrics
        psnr, ssim, sam = self._compute_iqa_metrics(generated_target, target)
        mse = F.mse_loss(generated_target, target)
        mae = F.l1_loss(generated_target, target)

        # Encapsulate into torch tensor
        output = torch.Tensor([mae, mse, psnr, ssim, sam, iou_generated, iou_real])
        return output

    def test_epoch_end(self, outputs):
        """LightningModule test epoch end hook

        Args:
            outputs (list[torch.Tensor]): list of test steps outputs

        Returns:
            type: dict
        """
        # Average metrics
        outputs = torch.stack(outputs).mean(dim=0)
        mae, mse, psnr, ssim, sam, iou_estimated, iou_real = outputs
        iou_ratio = iou_estimated / iou_real

        # Make and dump logs
        output = {'test_mae': mae.item(),
                  'test_mse': mse.item(),
                  'test_psnr': psnr.item(),
                  'test_ssim': ssim.item(),
                  'test_sam': sam.item(),
                  'test_jaccard_generated_samples': iou_estimated.item(),
                  'test_jaccard_real_samples': iou_real.item(),
                  'test_jaccard_ratio': iou_ratio.item()}
        return {'log': output}

    @property
    def generator(self):
        return self.model

    @property
    def discriminator(self):
        return self._discriminator

    @property
    def l1_weight(self):
        return self._l1_weight

    @discriminator.setter
    def discriminator(self, discriminator):
        self._discriminator = discriminator

    @l1_weight.setter
    def l1_weight(self, l1_weight):
        self._l1_weight = l1_weight

    @classmethod
    def _make_build_kwargs(self, cfg, test=False):
        """Build keyed arguments dictionnary out of configurations to be passed
            to class constructor

        Args:
            cfg (dict): loaded YAML configuration file
            test (bool): set to True for testing

        Returns:
            type: dict
        """
        build_kwargs = {'generator': build_model(cfg['model']['generator']),
                        'discriminator': build_model(cfg['model']['discriminator']),
                        'dataset': build_dataset(cfg['dataset']),
                        'split': list(cfg['dataset']['split'].values()),
                        'optimizer_kwargs': cfg['optimizer'],
                        'lr_scheduler_kwargs': cfg['lr_scheduler'],
                        'dataloader_kwargs': cfg['dataset']['dataloader'],
                        'seed': cfg['experiment']['seed']}
        if test:
            reference_classifier = load_pickle(cfg['testing']['reference_classifier_path'])
            build_kwargs.update({'reference_classifier': reference_classifier})
        else:
            build_kwargs.update({'l1_weight': cfg['experiment']['l1_regularization_weight']})
        return build_kwargs


@EXPERIMENTS.register('cgan_toy_cloud_removal_upper_bound')
class cGANToyAlreadyClean(cGANToyCloudRemoval):
    """Overrides cGANToyCloudRemoval to instead feed the model with already clean
    images.

    This way, we establish an empirical performance upper bound for
    our model

                                 +-----------+
                                 +           +
               clean_optical --->| Generator |---> predicted_clean_optical
                                 +           +
                                 +-----------+

    Args:
        generator (nn.Module)
        discriminator (nn.Module)
        dataset (ToyCloudRemovalDataset)
        split (list[float]): dataset split ratios in [0, 1] as [train, val]
            or [train, val, test]
        l1_weight (float): weight of l1 regularization term
        dataloader_kwargs (dict): parameters of dataloaders
        optimizer_kwargs (dict): parameters of optimizer defined in LightningModule.configure_optimizers
        lr_scheduler_kwargs (dict): paramters of lr scheduler defined in LightningModule.configure_optimizers
        reference_classifier (sklearn.BaseEstimator): reference pixelwise timeserie classifier for evaluation
        seed (int): random seed (default: None)
    """
    def train_dataloader(self):
        """Implements LightningModule train loader building method
        """
        # Make dataloader of (source, target) - no annotation needed
        self.train_set.dataset.use_annotations = False

        # Subsample from dataset to avoid having too many similar views from same time serie
        train_set = self._regular_subsample(dataset=self.train_set,
                                            subsampling_rate=5)

        # Instantiate loader
        train_loader_kwargs = self.dataloader_kwargs.copy()
        train_loader_kwargs.update({'dataset': train_set,
                                    'shuffle': True,
                                    'collate_fn': collate.target_as_input})
        loader = DataLoader(**train_loader_kwargs)
        return loader

    def val_dataloader(self):
        """Implements LightningModule validation loader building method
        """
        # Make dataloader of (source, target) - no annotation needed
        self.val_set.dataset.use_annotations = False

        # Instantiate loader
        val_loader_kwargs = self.dataloader_kwargs.copy()
        val_loader_kwargs.update({'dataset': self.val_set,
                                  'collate_fn': collate.target_as_input})
        loader = DataLoader(**val_loader_kwargs)
        return loader

    def test_dataloader(self):
        """Implements LightningModule test loader building method
        """
        # Make dataloader of (source, target, annotation)
        self.test_set.dataset.use_annotations = True

        # Instantiate loader with batch size = horizon s.t. full time series are loaded
        test_loader_kwargs = self.dataloader_kwargs.copy()
        test_loader_kwargs.update({'dataset': self.test_set,
                                   'batch_size': self.test_set.dataset.horizon,
                                   'collate_fn': collate.annotated_target_as_input})
        loader = DataLoader(**test_loader_kwargs)
        return loader

    def on_epoch_end(self):
        """Implements LightningModule end of epoch operations
        """
        # Compute generated samples out of logging images
        source, target = self.logger._logging_images
        with torch.no_grad():
            output = self(source)

        if self.current_epoch == 0:
            # Log input and groundtruth once only at first epoch
            self.logger.log_images(source[:, :3], tag='Source - Optical (fake RGB)', step=self.current_epoch)
            self.logger.log_images(target[:, :3], tag='Target - Optical (fake RGB)', step=self.current_epoch)

        # Log generated image at current epoch
        self.logger.log_images(output[:, :3], tag='Generated - Optical (fake RGB)', step=self.current_epoch)
