# Spatial and Temporal Evaluation of Deep Generative Models in Remote Sensing
Toy experimental setup for evaluating relevance of deep generative models in remote sensing applications


## Getting Started

- __(i) Generate__ synthetic remote sensing-like imagery dataset with variable adjustable characteristics (spatial resolution, temporal resolution, tangential scale distortion, cloud contamination, speckle noise)
- __(ii) Train__ a deep generative image translation model on dataset
- __(iii) Evaluate__ generated samples against dataset groundtruth at land-cover time series classification benchmark

<p align="center">
<img src="https://github.com/Cervest/ds-gan-spatiotemporal-evaluation/blob/master/docs/source/img/latent_vs_derived.png" alt="Ideal image and derived coarser one" width="1000"/>
 </p>

### Synthetic imagery generation

- __Generation step__ : _synthetize an ideal latent product_
- __Derivation step__ : _degrade latent product to match desired characteristics (resolution, corruption etc)_

Setup YAML configuration files specifying _generation_ and _derivation_ steps. Templates are proposed [here](https://github.com/Cervest/ds-gan-spatiotemporal-evaluation/tree/master/src/toygeneration/config/templates).

Execute generation as:

```bash
$ python run_toy_generation.py --cfg=path/to/generation/config.yaml --o=path/to/latent_product
Generation |################################| 31/31

$ python run_toy_derivation.py --cfg=path/to/derivation/config.yaml --o=path/to/derived_product
Derivation |#################               | 16/31
```

For generation as for derivation, created frames have an instance segmentation and classification annotation masks. Explicitely, output directories are structured as:
```
 ├── frames/           # 1 frame = 1 time step
 │   ├── frame_0.h5
 │   ├── ...
 │   └── frame_31.h5
 ├── annotations/      # frames associated annotation masks
 │   ├── annotation_0.h5
 │   ├── ...
 │   └── annotation_31.h5
 └── index.json
 ```

<p align="center">
<img src="https://github.com/Cervest/ds-gan-spatiotemporal-evaluation/blob/master/docs/source/img/latent_product.png" alt="Ideal product and annotation masks" width="700"/>
</p>


### Image Translation Model training


Setup YAML configuration files specifying training : dataset, model, optimizer, experiment. Examples are proposed [here](https://github.com/Cervest/ds-gan-spatiotemporal-evaluation/tree/master/src/rsgan/config).

Execute training on, say GPU 0, as:
```bash
$ python run_training.py --cfg=path/to/config.yaml --o=output/directory --device=0
```


### Spatiotemporal Evaluation of Image Translation Model

- __Make reference classifier__ _for land-cover classification task on dataset as an evaluation proxy for generated images_
- __Evaluate__ _generated images quality and performance against groundtruth when fed to reference classifier_


Specify reference classifier parameters and image translation model checkpoint to evaluate in YAML file previously defined for training execution.

Execute:
```bash
$ python make_reference_classifier.py --cfg=path/to/experiment/config.yaml --o=output/directory
$ python run_testing.py --cfg=path/to/experiment/config.yaml --o=output/directory --device=0
```


### Existing experiments

| Experiment                         | MAE   | MSE   | PSNR | SSIM  | SAM   | Jaccard Generated | Jaccard Groundtruth | Jaccard Ratio |
|------------------------------------|-------|-------|------|-------|-------|-------------------|---------------------|---------------|
| [cGAN Cloud Removal](https://github.com/Cervest/ds-gan-spatiotemporal-evaluation/blob/master/src/rsgan/experiments/cloud_removal/cgan_toy_cloud_removal.py#L14)                 | 0.246 | 0.129 | 17.9 | 0.687 | 0.174 | 0.493             | 0.993               | 0.496         |
| [Frame-recurrent cGAN Cloud Removal](https://github.com/Cervest/ds-gan-spatiotemporal-evaluation/blob/master/src/rsgan/experiments/cloud_removal/cgan_frame_recurrent_toy_cloud_removal.py#L12) | 0.200 | 0.074 | 21.2 | 0.825 | 0.147 | 0.553             | 0.993               | 0.556         |
| [cGAN Identity](https://github.com/Cervest/ds-gan-spatiotemporal-evaluation/blob/master/src/rsgan/experiments/cloud_removal/cgan_toy_cloud_removal.py#L395)                      | 0.043 | 0.003 | 31.8 | 0.99  | 0.092 | 0.980             | 0.993               | 0.986         |

_Score table averaged for 5 distinct seeds over testing set; "Jaccard Generated": Average Jaccard Index of reference classifier when evaluated on generated images; "Jaccard Groundtruth": Average Jaccard Index of reference classifier when evaluated on groundtruth images; "Jaccard Ratio": Jaccard Generated / Jaccard Groundtruth_

## Overview

### Organization

The repository is structured as follows :

```
├── data/
├── docs/
├── repro/
├── src/
├── tests/
├── utils/
├── make_reference_classifier.py
├── run_training.py
├── run_testing.py
├── run_toy_generation.py
└── run_toy_derivation.py
```

__Directories :__
- `data/` : Time series datasets used for toy product generation, generated toy datasets and experiments outputs
- `docs/`: any paper, notes, image relevant to this repository
- `src/`: all modules to run synthetic data generation and experiments
- `tests/`: unit testing
- `utils/`: miscellaneous utilities

---

__`src/` directory is then subdivided into :__

> __Synthetic data generation__ :
```
.
└── toygeneration
    ├── config/
    ├── blob/
    ├── timeserie/
    ├── modules/
    ├── derivation.py
    ├── export.py
    └── product.py
```
- `config/`: YAML configuration specification files for generation and derivation
- `blob/`: Modules implementing blobs such as voronoi polygons which are used in synthetic product
- `timeserie/`: Modules implementing time series handling to animate blobs
- `modules/`: Additional modules used for randomization of pixels, polygons computation, degradation effects
- `derivation.py`: Image degradation module
- `export.py`: Synthetic images dumping and loading
- `product.py`: Main synthetic imagery product generation module


> __Image-translation experiments__ :
```
.
└── rsgan/
    ├── config/
    ├── callbacks/
    ├── data/
    │   └── datasets/
    ├── evaluation
    │   └── metrics/
    ├── experiments
    │   ├── cloud_removal/
    │   ├── sar_to_optical/
    │   ├── experiment.py
    │   └── utils/
    └── models/
```
- `config/`: YAML configuration specification files for training and testing of models
- `callbacks/`: Experiment execution callback modules
- `data/`: Modules for used imagery datasets loading
- `evaluation/`: Misc useful modules for evaluation
- `experiments/`: Main directory proposing classes encapsulating each experiment
- `models`: Neural networks models used in experiments


## Installation

Code implemented in Python 3.8

#### Setting up environment

Clone and go to repository
```bash
$ git clone https://github.com/Cervest/ds-gan-spatiotemporal-evaluation.git
$ cd ds-gan-spatiotemporal-evaluation
```

Create and activate environment
```bash
$ pyenv virtualenv 3.8.2 gan-eval
$ pyenv activate gan-eval
$ (gan-eval)
```

Install dependencies
```bash
$ (gan-eval) pip install -r requirements.txt
```

#### Setting up dvc

From the environment and root project directory, you first need to build
symlinks to data directories as:
```bash
$ (gan-eval) dvc init -q
$ (gan-eval) python repro/dvc.py --link=where/data/stored --cache=where/cache/stored
```
if no `link` specified, data will be stored by default into `data/` directory and default cache is `.dvc/cache`.

To reproduce full pipeline, execute:
```bash
$ (gan-eval) dvc repro
```
In case pipeline is broken, hidden bash files are provided under `repro` directory

## References
