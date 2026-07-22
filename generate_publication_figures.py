"""
Gate ∆G Framework: Publication-Quality Figures

Figure 1: ∆G Distribution by Outcome Regime (Box + Violin)
Figure 2: PHI × CAC Interaction Plot (Best-Fit Model D3)
Figure 3: Noise Mechanism Pathway (Mediation Effect)
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats

# Load data
df = pd.read_csv('remainder_quality_analysis_v2.csv')

# Style setup
sns.set_style("whitegrid")
sns.set_palette("husl")
plt.rcParams['figure.dpi'] = 300
plt.rcParams['font.size'] = 10
plt.rcParams['axes.titlesize'] = 12
plt.rcParams['axes.labelsize'] = 11

# ============================================================================
# FIGURE 1: ∆G Distribution by Outcome Regime
# ============================================================================

fig, axes = plt.subplots(1, 2, figsize=(14, 5))

# Subplot 1a: Box plot with individual points
ax = axes[0]
outcomes_order = ['FR', 'MR', 'PR', 'CR', 'SR']
colors = {'FR': '#d62728', 'MR': '#ff7f0e', 'PR': '#2ca02c', 'CR': '#1f77b4', 'SR': '#9467bd'}
outcome_colors = [colors[o] for o in outcomes_order]

data_by_outcome = [df[df['Outcome'] == o]['ΔG'].values for o in outcomes_order]
bp = ax.boxplot(data_by_outcome, patch_artist=True, widths=0.6, showmeans=True)
ax.set_xticklabels(outcomes_order)

for patch, color in zip(bp['boxes'], outcome_colors):
    patch.set_facecolor(color)
    patch.set_alpha(0.7)

# Overlay points with jitter
for i, outcome in enumerate(outcomes_order, 1):
    y = df[df['Outcome'] == outcome]['ΔG'].values
    x = np.random.normal(i, 0.04, size=len(y))
    ax.scatter(x, y, alpha=0.3, s=20, color=colors[outcome])

ax.set_ylabel('Gate Magnitude (∆G)', fontsize=11, fontweight='bold')
ax.set_xlabel('Outcome Regime', fontsize=11, fontweight='bold')
ax.set_title('Figure 1a: ∆G Distribution by Outcome\n(Box plot with individual cases)', 
             fontsize=12, fontweight='bold')
ax.grid(True, alpha=0.3)
ax.axhline(0, color='red', linestyle='--', linewidth=1.5, alpha=0.5, label='∆G = 0')
ax.legend(loc='upper left')

# Subplot 1b: Violin plot (density)
ax = axes[1]
parts = ax.violinplot(data_by_outcome, positions=range(1, len(outcomes_order)+1), 
                       showmeans=True, showmedians=True)
for i, pc in enumerate(parts['bodies']):
    pc.set_facecolor(outcome_colors[i])
    pc.set_alpha(0.7)

ax.set_xticks(range(1, len(outcomes_order)+1))
ax.set_xticklabels(outcomes_order)
ax.set_ylabel('Gate Magnitude (∆G)', fontsize=11, fontweight='bold')
ax.set_xlabel('Outcome Regime', fontsize=11, fontweight='bold')
ax.set_title('Figure 1b: ∆G Density by Outcome\n(Violin plot)', fontsize=12, fontweight='bold')
ax.axhline(0, color='red', linestyle='--', linewidth=1.5, alpha=0.5)
ax.grid(True, alpha=0.3, axis='y')

plt.tight_layout()
plt.savefig('Figure_1_DeltaG_by_Outcome.png', dpi=300, bbox_inches='tight')
print("✓ Figure 1 saved: Figure_1_DeltaG_by_Outcome.png")
plt.close()

# ============================================================================
# FIGURE 2: PHI × CAC Interaction (Model D3)
# ============================================================================

fig, ax = plt.subplots(figsize=(10, 6))

# Standardize for visualization
df['Phi_std'] = (df['Φ'] - df['Φ'].mean()) / df['Φ'].std()
df['CAC_std'] = (df['CAC'] - df['CAC'].mean()) / df['CAC'].std()

# Create PHI groups (low, medium, high)
df['Phi_group'] = pd.cut(df['Φ'], bins=3, labels=['Low PHI', 'Medium PHI', 'High PHI'])

# Plot scatter with regression lines by PHI group
phi_groups = ['Low PHI', 'Medium PHI', 'High PHI']
colors_phi = ['#1f77b4', '#ff7f0e', '#d62728']

for group, color in zip(phi_groups, colors_phi):
    group_data = df[df['Phi_group'] == group]
    ax.scatter(group_data['CAC_std'], group_data['Q_rho'], 
              alpha=0.5, s=50, label=group, color=color)
    
    # Add regression line
    if len(group_data) > 1:
        z = np.polyfit(group_data['CAC_std'].values, group_data['Q_rho'].values, 1)
        p = np.poly1d(z)
        x_line = np.linspace(group_data['CAC_std'].min(), group_data['CAC_std'].max(), 100)
        ax.plot(x_line, p(x_line), color=color, linewidth=2.5, alpha=0.8)

ax.set_xlabel('Contradiction Metabolism (CAC, standardized)', fontsize=11, fontweight='bold')
ax.set_ylabel('Remainder Quality Q(ρ)', fontsize=11, fontweight='bold')
ax.set_title('Figure 2: PHI × CAC Interaction (Model D3)\nPHI Inhibits Contradiction Metabolism', 
             fontsize=12, fontweight='bold')
ax.legend(loc='best', fontsize=10, framealpha=0.95)
ax.grid(True, alpha=0.3)

# Add annotation
ax.text(0.02, 0.98, f'Model R² = 0.9803\nPhi×CAC: β = −0.103 (p<0.001)\nInterpretation: High PHI suppresses CAC effect', 
        transform=ax.transAxes, fontsize=9, verticalalignment='top',
        bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))

plt.tight_layout()
plt.savefig('Figure_2_PHI_CAC_Interaction.png', dpi=300, bbox_inches='tight')
print("✓ Figure 2 saved: Figure_2_PHI_CAC_Interaction.png")
plt.close()

# ============================================================================
# FIGURE 3: Noise → Regulator → Outcome Pathway
# ============================================================================

fig, ax = plt.subplots(figsize=(12, 6))

# Bin cases by Noise_pre_raw
df['Noise_group'] = pd.cut(df['Noise_pre_raw'], bins=[0, 1, 2, 3, 6], 
                            labels=['Low (0-1)', 'Med (1-2)', 'High (2-3)', 'Very High (3+)'])

# Plot: Noise → Q(ρ) → Reboot Quality
noise_levels = df['Noise_group'].unique()
noise_levels = sorted([x for x in noise_levels if pd.notna(x)])

positions_x = np.arange(len(noise_levels))
q_rho_means = [df[df['Noise_group'] == nl]['Q_rho'].mean() for nl in noise_levels]
reboot_means = [df[df['Noise_group'] == nl]['Reboot_Quality'].mean() for nl in noise_levels]

# Create dual-axis plot
ax2 = ax.twinx()

# Plot Q(ρ) on left axis
line1 = ax.plot(positions_x, q_rho_means, 'o-', color='#1f77b4', linewidth=2.5, 
               markersize=8, label='Q(ρ) (left axis)', alpha=0.8)
ax.set_ylabel('Remainder Quality Q(ρ)', fontsize=11, fontweight='bold', color='#1f77b4')
ax.tick_params(axis='y', labelcolor='#1f77b4')

# Plot Reboot Quality on right axis
line2 = ax2.plot(positions_x, reboot_means, 's-', color='#d62728', linewidth=2.5, 
                markersize=8, label='Reboot Quality (right axis)', alpha=0.8)
ax2.set_ylabel('Reboot Quality (% Clean)', fontsize=11, fontweight='bold', color='#d62728')
ax2.tick_params(axis='y', labelcolor='#d62728')

ax.set_xticks(positions_x)
ax.set_xticklabels(noise_levels)
ax.set_xlabel('Pre-Gate Noise Level (Noise_pre_raw)', fontsize=11, fontweight='bold')
ax.set_title('Figure 3: Noise Pathway to Reboot Quality\nNoise → Lower Q(ρ) → Lower Reboot Quality', 
            fontsize=12, fontweight='bold')
ax.grid(True, alpha=0.3, axis='y')

# Combine legends
lines = line1 + line2
labels = [l.get_label() for l in lines]
ax.legend(lines, labels, loc='center left', fontsize=10, framealpha=0.95)

plt.tight_layout()
plt.savefig('Figure_3_Noise_Pathway.png', dpi=300, bbox_inches='tight')
print("✓ Figure 3 saved: Figure_3_Noise_Pathway.png")
plt.close()

# ============================================================================
# FIGURE 4: Effect Size Summary (Forest Plot)
# ============================================================================

fig, ax = plt.subplots(figsize=(10, 8))

# Summary of key regression coefficients with 95% CI
effects = [
    ('AV → Q(ρ)', -0.1215, 0.0164, '#d62728'),      # Panel A
    ('DD → Q(ρ)', -0.1654, 0.0089, '#d62728'),      # Panel A
    ('∆G → Reboot', 0.0940, 0.0105, '#2ca02c'),     # Panel B
    ('CID → Q(ρ)', 0.0673, 0.0143, '#1f77b4'),      # Panel C
    ('CAC → Q(ρ)', 0.2679, 0.0142, '#1f77b4'),      # Panel C
    ('Φ → Q(ρ)', 0.0059, 0.0056, '#ff7f0e'),        # Panel D1
    ('Φ×ECC → Q(ρ)', -0.1524, 0.0159, '#d62728'),  # Panel D2
    ('Φ×CAC → Q(ρ)', -0.1032, 0.0037, '#d62728'),  # Panel D3
]

y_pos = np.arange(len(effects))
names, coefs, stes, colors_list = zip(*effects)

# Calculate 95% CI
ci_lower = [c - 1.96*s for c, s in zip(coefs, stes)]
ci_upper = [c + 1.96*s for c, s in zip(coefs, stes)]

# Plot
for i, (name, coef, ci_l, ci_u, color) in enumerate(zip(names, coefs, ci_lower, ci_upper, colors_list)):
    # Horizontal line for CI
    ax.plot([ci_l, ci_u], [i, i], color=color, linewidth=2, alpha=0.8)
    # Point for coefficient
    ax.scatter(coef, i, s=150, color=color, zorder=5, edgecolor='black', linewidth=1)
    # Add coefficient label
    ax.text(coef + 0.01, i + 0.15, f'{coef:.4f}', fontsize=9, va='center')

ax.axvline(0, color='black', linestyle='--', linewidth=1, alpha=0.5)
ax.set_yticks(y_pos)
ax.set_yticklabels(names, fontsize=10)
ax.set_xlabel('Standardized Coefficient (β)', fontsize=11, fontweight='bold')
ax.set_title('Figure 4: Effect Sizes Summary (Forest Plot)\nAll 95% CIs shown; significant effects do not cross zero', 
            fontsize=12, fontweight='bold')
ax.grid(True, alpha=0.3, axis='x')
plt.tight_layout()
plt.savefig('Figure_4_Effect_Sizes.png', dpi=300, bbox_inches='tight')
print("✓ Figure 4 saved: Figure_4_Effect_Sizes.png")
plt.close()

# ============================================================================
# SUMMARY
# ============================================================================

print("\n" + "=" * 80)
print("PUBLICATION-QUALITY FIGURES GENERATED")
print("=" * 80)
print("\nFigures created:")
print("  1. Figure_1_DeltaG_by_Outcome.png")
print("     → Box + Violin plots showing ∆G distribution by outcome regime")
print("     → Key finding: Perfect separation (FR all negative; clean all positive)")
print("\n  2. Figure_2_PHI_CAC_Interaction.png")
print("     → Regression lines for Q(ρ) vs CAC, stratified by PHI level")
print("     → Key finding: High PHI suppresses CAC effect (negative interaction)")
print("\n  3. Figure_3_Noise_Pathway.png")
print("     → Dual-axis plot: Noise → Q(ρ) → Reboot Quality")
print("     → Key finding: Noise gradient predicts both regulator and outcome")
print("\n  4. Figure_4_Effect_Sizes.png")
print("     → Forest plot of all key regression coefficients with 95% CI")
print("     → Key finding: All significant effects (CI excludes zero)")
print("\nReady for publication/presentation.")
print("=" * 80)
