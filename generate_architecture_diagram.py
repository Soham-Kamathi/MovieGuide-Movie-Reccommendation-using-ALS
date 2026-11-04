import matplotlib.pyplot as plt
import matplotlib.patches as patches
from pathlib import Path

# Create output dir
out_dir = Path("artifacts/report_assets")
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / "figure1_architecture.png"

fig, ax = plt.subplots(figsize=(16, 10), dpi=300)
ax.set_xlim(0, 16)
ax.set_ylim(0, 10)
ax.axis("off")

# Colors
BG_COLOR = "#FAFBFC"
fig.patch.set_facecolor(BG_COLOR)
ax.set_facecolor(BG_COLOR)

# Tier Colors (Modern Tech Palette)
C_DATA = "#EBF3FB"       # Light Ice Blue
C_DATA_B = "#2B6CB0"     # Dark Slate Blue
C_PREP = "#E6FFFA"       # Light Mint
C_PREP_B = "#234E52"     # Deep Teal
C_MODEL = "#FAF5FF"      # Light Lavender
C_MODEL_B = "#553C9A"    # Deep Purple
C_SERV = "#FEFCBF"       # Soft Amber
C_SERV_B = "#744210"     # Rich Bronze
C_FUSION = "#FEEBC8"     # Light Orange
C_FUSION_B = "#7B341E"   # Deep Russet
C_UI = "#EDF2F7"         # Clean Slate
C_UI_B = "#1A202C"       # Near Black

def draw_block(ax, x, y, w, h, bg, border, title, items, subtitle=""):
    # Drop shadow
    shadow = patches.FancyBboxPatch((x + 0.08, y - 0.08), w, h, boxstyle="round,pad=0.1,rounding_size=0.15",
                                    facecolor="#000000", alpha=0.06, edgecolor="none", zorder=1)
    ax.add_patch(shadow)
    # Main Box
    box = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.1,rounding_size=0.15",
                                facecolor=bg, edgecolor=border, linewidth=1.8, zorder=2)
    ax.add_patch(box)
    
    # Title
    ax.text(x + w/2, y + h - 0.35, title, fontsize=11, fontweight="bold", color=border,
            ha="center", va="center", family="sans-serif", zorder=3)
    if subtitle:
        ax.text(x + w/2, y + h - 0.65, subtitle, fontsize=8.5, fontfamily="sans-serif",
                style="italic", color="#4A5568", ha="center", va="center", zorder=3)
        start_y = y + h - 0.95
    else:
        start_y = y + h - 0.70
        
    # Items
    for i, it in enumerate(items):
        ax.text(x + 0.2, start_y - (i * 0.32), it, fontsize=8.5, color="#2D3748",
                ha="left", va="center", family="sans-serif", zorder=3)

# 1. Title Banner
ax.text(8.0, 9.5, "movieguide: End-to-End System Architecture", fontsize=17, fontweight="bold",
        ha="center", va="center", color="#1A202C", family="sans-serif")
ax.text(8.0, 9.1, "Pure-Python Vectorized ALS Matrix Factorization with Hybrid Content & Bayesian Ranking",
        fontsize=10.5, style="italic", ha="center", va="center", color="#4A5568", family="sans-serif")

# Tiers Layout (Two rows of 3 columns or horizontal flow)
# Row 1: Data Layer -> Preprocessing & Splits -> Model Training
# Row 2: Service / Scoring -> Hybrid Fusion & Normalization -> Presentation (Streamlit)

# Tier 1: Data Storage & Ingestion
draw_block(ax, 0.8, 5.2, 4.2, 3.2, C_DATA, C_DATA_B, "1. Data Storage & Ingestion", [
    "• MovieLens 100k Dataset (ratings.csv, movies.csv)",
    "• GroupLens TLS/CA Verification & Ingestion",
    "• Data Validation (0.5 - 5.0 Star Bound Checking)",
    "• Deduplication (Timestamp-based resolution)",
    "• SQLite Database (recommendations.sqlite3):",
    "   - profiles (UUID, display_name, created_at)",
    "   - ratings (profile_id, movie_id, rating)"
], subtitle="Raw Sources & Persistence")

# Tier 2: Preprocessing & Chronological Split
draw_block(ax, 5.9, 5.2, 4.2, 3.2, C_PREP, C_PREP_B, "2. Preprocessing & Temporal Partitioning", [
    "• Chronological Per-User Sorting (zero data leakage)",
    "• Temporal Split Allocation:",
    "   - Train Split: 99,616 ratings (Historical interactions)",
    "   - Validation Split: 610 ratings (Penultimate rating)",
    "   - Test Split: 610 ratings (Final rating per user)",
    "• Contiguous ID Mapping (user_to_idx, movie_to_idx)",
    "• Sparse Matrix Generation (CSR / CSC formats)"
], subtitle="Leakage-Free Partitioning Pipeline")

# Tier 3: Core Training Engine
draw_block(ax, 11.0, 5.2, 4.2, 3.2, C_MODEL, C_MODEL_B, "3. Vectorized ALS Training Engine", [
    "• Multi-Pass Regularized Baseline Estimation:",
    "   - Global Mean (\u03bc = 3.5015), User (b_u), Item (b_i)",
    "• Alternating Least Squares (ALS) Optimization:",
    "   - User Factor Solve: U_u = (V^T V + \u03bb I)^(-1) V^T r_res",
    "   - Item Factor Solve: V_i = (U^T U + \u03bb I)^(-1) U^T r_res",
    "• Single-Thread OpenBLAS Execution (threadpoolctl)",
    "• Hyperparameter Tuning (rank=4, \u03bb=0.2, RMSE=0.9768)",
    "• Compressed Artifact Store (als_model.npz, config.json)"
], subtitle="Pure-Python Explicit Factorization")

# Row 2: Inference & Serving Layer
# Tier 4: Multi-Source Service Layer
draw_block(ax, 0.8, 0.8, 4.2, 3.4, C_SERV, C_SERV_B, "4. Multi-Source Candidate Retrieval", [
    "• Dynamic Profile Projection (New Users / Ratings):",
    "   - u_new = (V_obs^T V_obs + \u03bb I)^(-1) V_obs^T (r_obs - \u03bc - b_i)",
    "   - Fast sub-2ms edge solve without retraining",
    "• Genre Cosine Similarity Engine:",
    "   - 20-dim CountVectorizer binary genre vectors",
    "   - Profile centroid cosine matching on liked movies",
    "• Bayesian Shrinkage Popularity Prior:",
    "   - S_pop = (N_i * r\u0304_i + m*\u03bc) / (N_i + m), m=20 shrinkage",
    "• Cold-Start Smooth Degradation Protocol"
], subtitle="Collaborative, Content & Popularity Streams")

# Tier 5: Hybrid Fusion & Filtering
draw_block(ax, 5.9, 0.8, 4.2, 3.4, C_FUSION, C_FUSION_B, "5. Hybrid Normalization & Fusion", [
    "• Filter Visited Items (Exclude user's rated movies)",
    "• Min-Max Score Normalization across generators:",
    "   - S\u0303 = (S - min(S)) / (max(S) - min(S))",
    "• Weighted Linear Score Aggregation:",
    "   - S_hybrid = 0.70 * S\u0303_als + 0.20 * S\u0303_genre + 0.10 * S\u0303_pop",
    "• Top-K Partial Sort (argpartition for O(N) scaling)",
    "• Source Attribution Tagging (e.g. 'als+content+popularity')",
    "• 9.9x Catalog Coverage Expansion (7.12% vs 0.72%)"
], subtitle="Calibrated Score Blending")

# Tier 6: Streamlit UI & Feedback Loop
draw_block(ax, 11.0, 0.8, 4.2, 3.4, C_UI, C_UI_B, "6. Presentation & Interactive Discovery", [
    "• Streamlit Multi-Tab Web Interface (app.py):",
    "   - Tab 1: 'For you' (Personalized cards, IMDb/YouTube)",
    "   - Tab 2: 'Browse and rate' (Filters, search, 0.5-5.0 stars)",
    "   - Tab 3: 'Model notes' (Active model metrics & inspect)",
    "• Incremental Feedback Loop:",
    "   - New star ratings stored instantly to SQLite",
    "   - Dynamic profile projection updates recs instantly",
    "   - Appended to next scheduled batch ALS retraining"
], subtitle="Local Reactive Dashboard")

# Connecting Arrows
arrow_kw = dict(arrowstyle="->,head_width=0.4,head_length=0.6", lw=2.2, color="#4A5568")

# Row 1 Horizontal Arrows
ax.annotate("", xy=(5.8, 6.8), xytext=(5.1, 6.8), arrowprops=arrow_kw)
ax.annotate("", xy=(10.9, 6.8), xytext=(10.2, 6.8), arrowprops=arrow_kw)

# Downward Bridge: Model -> Candidate Retrieval / Service
ax.annotate("", xy=(3.0, 4.3), xytext=(12.5, 5.1),
            arrowprops=dict(arrowstyle="->,head_width=0.4,head_length=0.6", lw=2.0, color="#718096",
                            connectionstyle="arc3,rad=-0.25", linestyle="--"))
ax.text(7.6, 4.75, "Trained Latent Factors & Baselines", fontsize=8.5, fontweight="bold",
        color="#4A5568", ha="center", va="center", backgroundcolor="#FFFFFF", zorder=4)

# Row 2 Horizontal Arrows
ax.annotate("", xy=(5.8, 2.5), xytext=(5.1, 2.5), arrowprops=arrow_kw)
ax.annotate("", xy=(10.9, 2.5), xytext=(10.2, 2.5), arrowprops=arrow_kw)

# Feedback Loop: UI -> SQLite Data Layer
ax.annotate("", xy=(2.9, 5.1), xytext=(12.8, 4.3),
            arrowprops=dict(arrowstyle="->,head_width=0.4,head_length=0.6", lw=2.0, color="#E53E3E",
                            connectionstyle="arc3,rad=-0.22", linestyle=":"))
ax.text(8.0, 4.25, "\u21bb Incremental User Ratings Feedback Loop to SQLite", fontsize=8.5, fontweight="bold",
        color="#C53030", ha="center", va="center", backgroundcolor="#FFFFFF", zorder=4)

plt.tight_layout()
plt.savefig(out_path, dpi=300, bbox_inches="tight")
print(f"Diagram saved successfully to: {out_path}")
