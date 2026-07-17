# Machine Learning Architecture

This document provides a comprehensive overview of the end-to-end Machine Learning pipeline and model lifecycle within the project.

## 1. Pipeline Visualization

```mermaid
graph TD
    %% Input Layer
    A[Code Scanners / Uploaded ZIP] -->|Raw Findings| B[Data Ingestion]

    %% Feature Extraction Layer
    B --> C[Feature Extraction Module]
    C -->|Text / Code Snippets| D[Transformer Integration: microsoft/codebert-base]
    C -->|Structural / Metadata Features| E[Feature Vector Assembly]
    D -->|Contextual Embeddings| E

    %% ML Models Inference Layer
    E --> F[Model Inference Engine]
    F -->|Feature Matrix| G[Ranker Model: ranker.pkl]
    F -->|Feature Matrix| H[FP Classifier: fp_classifier.pkl]

    %% Output Processing Layer
    G -->|Risk Score / Priority| I[Post-Processing & Aggregation]
    H -->|Is False Positive? True/False| I
    
    %% Final Output
    I --> J[Final Refined JSON Output]
    J -->|Render UI / Report| K[Backend Dashboard]

    %% Styling
    style A fill:#f9f,stroke:#333,stroke-width:2px
    style G fill:#bbf,stroke:#333,stroke-width:2px
    style H fill:#bbf,stroke:#333,stroke-width:2px
    style K fill:#bfb,stroke:#333,stroke-width:2px
```

## 2. Component Breakdown

### A. Data Ingestion & Scanners
* Accepts raw code files via ZIP uploads or repository scans.
* Extracts structural syntax trees and raw text snippets containing suspected security vulnerabilities.

### B. Feature Extraction & Embedding
* Computes static properties like line counts, nesting depth, and confidence scores.
* Leverages `microsoft/codebert-base` to convert code tokens into fixed-size contextual embeddings.

### C. Predictive ML Models (`ranker.py` & `fp_predictor.py`)
* **Ranker Model (`ranker.pkl`)**: Assigns dynamic risk scores. Defaults to scanner severity if absent.
* **False Positive Classifier (`fp_classifier.pkl`)**: Identifies benign patterns. Assumes legitimate if absent.
