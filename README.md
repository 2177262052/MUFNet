# MUF-Net: A Novel Self-Attention Based Dual-Task Learning Approach for Automatic Left Ventricle Segmentation in Echocardiography

In this study, we propose a novel self-attention-based dual-task learning approach 8 for automatic left ventricle segmentation.

## Getting Started
if you want to train:
```
python train_new.py
```
If you want to test individual model weights：
```
run cs_weight.py
```
If you want to test calculated ESV and EDV
```
run test_only_new.py
run calculate_diff.py
```
If you want to visualize, visualization.py has some functions you can use
### Prerequisites
python3.8 ,pytorch and so on

## Training_weight
If you want to download training weights, here are some options：
* [Training weight92.79](http://www.dropwizard.io/1.0.2/docs/) 
* [Training weight92.69](https://maven.apache.org/)
* [Training weight92.54(ICIC)](https://rometools.github.io/rome/)


## License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details
