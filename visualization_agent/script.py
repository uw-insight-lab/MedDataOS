import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
from sklearn.metrics import confusion_matrix

# --- 1. Synthetic Data Generation ---
# In a real scenario, this data would be loaded from a file.
# We generate it here to make the script self-contained and reproducible.
np.random.seed(42)
num_samples = 500

data = {
    'Age': np.random.normal(loc=62, scale=12, size=num_samples).astype(int),
    'Smoking PY': np.random.exponential(scale=20, size=num_samples).astype(int),
    'Sex': np.random.choice(['Male', 'Female'], size=num_samples, p=[0.7, 0.3]),
    'ECOG PS': np.random.choice([0, 1, 2, 3], size=num_samples, p=[0.4, 0.35, 0.2, 0.05]),
    'Ds Site': np.random.choice(['Oropharynx', 'Larynx', 'Hypopharynx', 'Oral Cavity'], size=num_samples, p=[0.45, 0.25, 0.15, 0.15]),
    'N': np.random.choice(['N0', 'N1', 'N2', 'N3'], size=num_samples, p=[0.5, 0.25, 0.2, 0.05])
}
df = pd.DataFrame(data)

# Simulate model predictions for the confusion matrix
# We'll create predictions that are mostly correct but have some errors.
y_true = df['N']
y_pred = y_true.copy()
error_indices = np.random.choice(df.index, size=int(num_samples * 0.25), replace=False)
for idx in error_indices:
    # Get all possible labels except the true one
    possible_preds = [label for label in y_true.unique() if label != y_true[idx]]
    # Assign a random incorrect prediction
    y_pred[idx] = np.random.choice(possible_preds)

# --- 2. Visualization ---
# Set the overall style
sns.set_style("whitegrid")
plt.style.use('seaborn-v0_8-talk')

# Create a figure with subplots in a 3x3 grid
fig, axes = plt.subplots(3, 3, figsize=(22, 20))
fig.suptitle('Comprehensive Analysis of Patient and Disease Characteristics', fontsize=24, y=1.02)

# --- Feature Distributions ---

# Age Histogram
sns.histplot(data=df, x='Age', kde=True, ax=axes[0, 0], color='skyblue')
axes[0, 0].set_title('Distribution of Patient Age', fontsize=16)
axes[0, 0].set_xlabel('Age (years)')
axes[0, 0].set_ylabel('Frequency')

# Smoking PY Histogram
sns.histplot(data=df, x='Smoking PY', kde=True, ax=axes[0, 1], color='salmon')
axes[0, 1].set_title('Distribution of Smoking Pack-Years', fontsize=16)
axes[0, 1].set_xlabel('Smoking (Pack-Years)')
axes[0, 1].set_ylabel('Frequency')

# Sex Bar Chart
sns.countplot(data=df, x='Sex', ax=axes[0, 2], palette='viridis', order=df['Sex'].value_counts().index)
axes[0, 2].set_title('Frequency of Patient Sex', fontsize=16)
axes[0, 2].set_xlabel('Sex')
axes[0, 2].set_ylabel('Count')

# ECOG PS Bar Chart
sns.countplot(data=df, x='ECOG PS', ax=axes[1, 0], palette='plasma')
axes[1, 0].set_title('Frequency of ECOG Performance Status', fontsize=16)
axes[1, 0].set_xlabel('ECOG PS')
axes[1, 0].set_ylabel('Count')

# Disease Site Bar Chart
sns.countplot(data=df, y='Ds Site', ax=axes[1, 1], palette='magma', order=df['Ds Site'].value_counts().index)
axes[1, 1].set_title('Frequency of Disease Site', fontsize=16)
axes[1, 1].set_xlabel('Count')
axes[1, 1].set_ylabel('Disease Site')


# --- Target Variable Analysis ---
n_stage_order = sorted(df['N'].unique())
sns.countplot(data=df, x='N', ax=axes[1, 2], palette='cividis', order=n_stage_order)
axes[1, 2].set_title('Distribution of Target (N Stage)', fontsize=16)
axes[1, 2].set_xlabel('N Stage')
axes[1, 2].set_ylabel('Count')

# --- Feature Relationships ---
# Correlation Heatmap for numerical features
numerical_features = df.select_dtypes(include=np.number)
corr_matrix = numerical_features.corr()
sns.heatmap(corr_matrix, annot=True, cmap='coolwarm', fmt=".2f", ax=axes[2, 0], linewidths=.5)
axes[2, 0].set_title('Correlation Between Numerical Features', fontsize=16)

# --- Model Performance Visualization ---
# Confusion Matrix Heatmap
labels = sorted(y_true.unique())
cm = confusion_matrix(y_true, y_pred, labels=labels)
sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', ax=axes[2, 1], xticklabels=labels, yticklabels=labels)
axes[2, 1].set_title('Model Performance: Confusion Matrix', fontsize=16)
axes[2, 1].set_xlabel('Predicted N Stage')
axes[2, 1].set_ylabel('True N Stage')

# Turn off the empty subplot
axes[2, 2].axis('off')

# Adjust layout and save the figure
plt.tight_layout(rect=[0, 0, 1, 0.98])
plt.savefig('/Users/mbidnyj/Dev/multi-agent-system/visualization_agent/insight.png', dpi=300, bbox_inches='tight')