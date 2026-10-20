# ==============================================================================
# column_reporter.py - Visualization & Report Generation Engine (ACI 318-14)
# Features: 2D Cross-Section Plotter, P-M Diagram Plotter, Math Proof Generator
# ==============================================================================

from typing import Any

import matplotlib.pyplot as plt
from matplotlib import patches

from column_models import ColumnInputData


# ------------------------------------------------------------------------------
# 1. 2D CROSS-SECTION VISUALIZATION ENGINE
# ------------------------------------------------------------------------------
def plot_column_section(data: ColumnInputData, props: dict[str, Any], slenderness: dict[str, Any] | None = None) -> plt.Figure:
    """
    Generates a 2D engineering drawing of the reinforced concrete column section.
    Displays concrete boundaries, ties, main rebars, and dimensional labels.
    """
    b = data.b
    h = data.h
    covering = data.covering
    tie_db_cm = data.tie_data.tie_dia / 10.0

    fig, ax = plt.subplots(figsize=(5, 5), dpi=100)
    ax.set_aspect("equal")

    # Concrete outer boundary
    concrete_rect = patches.Rectangle(
        (-b / 2.0, -h / 2.0), b, h,
        linewidth=2, edgecolor="#1e293b", facecolor="#e2e8f0", label="Concrete"
    )
    ax.add_patch(concrete_rect)

    # Transverse tie perimeter
    tie_w = b - (2.0 * covering)
    tie_h = h - (2.0 * covering)
    if tie_w > 0 and tie_h > 0:
        tie_rect = patches.Rectangle(
            (-tie_w / 2.0, -tie_h / 2.0), tie_w, tie_h,
            linewidth=1.5, edgecolor="#0284c7", facecolor="none", linestyle="--", label="Tie Bar"
        )
        ax.add_patch(tie_rect)

    if slenderness is None:
        slenderness = {}

    # Main longitudinal rebars
    critical_end = slenderness.get("critical_end", "Top")
    Mu_top = data.forces.Mu_top
    Mu_bot = data.forces.Mu_bot
    Mu_crit = Mu_top if critical_end == "Top" else Mu_bot

    if Mu_crit >= 0:
        top_text, bot_text = "[C] COMPRESSION FACE", "[T] TENSION FACE"
        top_color, bot_color = "#38BDF8", "#EF4444"
    else:
        top_text, bot_text = "[T] TENSION FACE", "[C] COMPRESSION FACE"
        top_color, bot_color = "#EF4444", "#38BDF8"

    ax.text(0, (h / 2.0) + 3.0, f"{top_text} ({critical_end} M2)", color=top_color, 
            fontsize=9, fontweight="bold", ha="center", va="bottom")
    ax.text(0, -(h / 2.0) - 3.0, bot_text, color=bot_color, 
            fontsize=9, fontweight="bold", ha="center", va="top")
    rebars = props.get("processed_rebars", [])
    first_rebar = True
    for layer in rebars:
        qty = layer["qty_i"]
        db_cm = layer["db_i"] / 10.0
        y_pos = layer["y_dist_i"]

        # Calculate horizontal distribution across section width
        if qty == 1:
            x_positions = [0.0]
        else:
            x_start = -(tie_w / 2.0) + tie_db_cm + (db_cm / 2.0)
            x_end = (tie_w / 2.0) - tie_db_cm - (db_cm / 2.0)
            step = (x_end - x_start) / max(1, qty - 1)
            x_positions = [x_start + i * step for i in range(qty)]

        for x_pos in x_positions:
            circle = patches.Circle(
                (x_pos, -y_pos), db_cm / 2.0,
                facecolor="#dc2626", edgecolor="#7f1d1d", linewidth=1,
                label="Main Rebar" if first_rebar else ""
            )
            ax.add_patch(circle)
            first_rebar = False

    # Set chart boundaries and guidelines
    margin = max(b, h) * 0.25
    ax.set_xlim(-b / 2.0 - margin, b / 2.0 + margin)
    ax.set_ylim(-h / 2.0 - margin, h / 2.0 + margin)

    # Add axis centerlines
    ax.axhline(0, color="#94a3b8", linestyle=":", linewidth=0.8)
    ax.axvline(0, color="#94a3b8", linestyle=":", linewidth=0.8)

    # Title & Dimension Annotation
    ax.set_title(f"Column Cross-Section ({b:.0f} x {h:.0f} cm)", fontsize=11, fontweight="bold", pad=10)
    ax.text(0, -h / 2.0 - (margin * 0.5), f"b = {b:.1f} cm", ha="center", va="top", fontsize=9, fontweight="bold")
    ax.text(-b / 2.0 - (margin * 0.5), 0, f"h = {h:.1f} cm", ha="right", va="center", rotation=90, fontsize=9, fontweight="bold")

    ax.axis("off")
    fig.tight_layout()
    return fig


# ------------------------------------------------------------------------------
# 2. P-M INTERACTION DIAGRAM VISUALIZATION ENGINE
# ------------------------------------------------------------------------------
def plot_interaction_diagram(diagram: dict[str, Any], demand: dict[str, Any]) -> plt.Figure:
    """
    Plots nominal and design P-M interaction curves alongside the factored demand point (Mc, Pu).
    """
    nom_curve = diagram["nominal_curve"]
    des_curve = diagram["design_curve"]

    # Extract curve coordinates (Convert kg to ton, kg-m to ton-m)
    nom_M = [pt["Mn"] / 1000.0 for pt in nom_curve]
    nom_P = [pt["Pn"] / 1000.0 for pt in nom_curve]

    des_M = [pt["phi_Mn"] / 1000.0 for pt in des_curve]
    des_P = [pt["phi_Pn"] / 1000.0 for pt in des_curve]

    Pu_ton = demand["Pu"] / 1000.0
    Mc_ton = demand["Mc"] / 1000.0

    fig, ax = plt.subplots(figsize=(6, 5), dpi=100)

    # Plot Nominal & Design Capacity Envelopes
    ax.plot(nom_M, nom_P, color="#94a3b8", linestyle="--", linewidth=1.5, label="Nominal Curve (Pn, Mn)")
    ax.plot(des_M, des_P, color="#0284c7", linewidth=2.0, label="Design Envelope (φPn, φMn)")

    # Plot Maximum Axial Compression Cap Line
    phi_Pn_max_ton = diagram["phi_Pn_max"] / 1000.0
    ax.axhline(phi_Pn_max_ton, color="#e11d48", linestyle=":", linewidth=1.2, label=f"Max Cap = {phi_Pn_max_ton:.1f} t")

    # Plot Factored Demand Point (Mc, Pu)
    demand_color = "#16a34a" if demand.get("shear_status", "PASS") == "PASS" else "#dc2626"
    ax.scatter([Mc_ton], [Pu_ton], color=demand_color, s=70, zorder=5, label=f"Demand (Mc={Mc_ton:.1f} t-m, Pu={Pu_ton:.1f} t)")

    # Formatting & Grid
    ax.set_xlabel("Bending Moment, M (ton-m)", fontsize=10, fontweight="bold")
    ax.set_ylabel("Axial Force, P (ton)", fontsize=10, fontweight="bold")
    ax.set_title("P-M Interaction Diagram (ACI 318-14)", fontsize=11, fontweight="bold", pad=12)
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.axhline(0, color="#475569", linewidth=0.8)
    ax.axvline(0, color="#475569", linewidth=0.8)
    ax.legend(fontsize=8, loc="upper right", frameon=True)

    fig.tight_layout()
    return fig


# ------------------------------------------------------------------------------
# 3. TEXT & MATHEMATICAL PROOF SHEET GENERATOR
# ------------------------------------------------------------------------------
def generate_text_report(data: ColumnInputData, results: dict[str, Any]) -> str:
    """
    Generates a structured ASCII mathematical proof document detailing step-by-step
    column analysis according to ACI 318-14.
    """
    props = results["section_properties"]
    slend = results["slenderness_and_shear"]
    diagram = results["interaction_diagram"]
    safety = results["safety_verification"]

    lines = [
        "=" * 78,
        "          ACI 318-14 RC COLUMN ANALYSIS & DESIGN PROOF SHEET          ",
        "=" * 78,
        f"Section Geometry : b = {data.b:.1f} cm, h = {data.h:.1f} cm, Cover = {data.covering:.1f} cm",
        f"Material Strengths: f'c = {data.fc_prime:.0f} ksc, fy = {data.fy:.0f} ksc, fyt = {data.fyt:.0f} ksc",
        "-" * 78,
        "1. SECTION PROPERTIES & REINFORCEMENT",
        f"   - Gross Concrete Area (Ag)     = {props['Ag']:.2f} cm²",
        f"   - Moment of Inertia (Ig)       = {props['Ig']:.2f} cm⁴",
        f"   - Radius of Gyration (r)       = {props['r']:.3f} cm",
        f"   - Total Longitudinal Steel (Ast)= {props['Ast']:.2f} cm²",
        f"   - Reinforcement Ratio (rho_g)  = {props['rho_g'] * 100:.2f}%",
        "-" * 78,
        "2. SLENDERNESS & MOMENT MAGNIFICATION (ACI 318-14 Sec 6.2)",
        f"   - Unsupported Length (Lu)      = {data.Lu:.2f} m",
        f"   - Effective Length Factor (K)  = {max(data.K_x, data.K_y):.2f}",
        f"   - Calculated Slenderness (Kl/r)= {slend['slenderness_ratio']:.2f}",
        f"   - Slenderness Limit            = {slend['limit']:.2f}",
        f"   - Column Classification        = {'SLENDER (Magnified)' if slend['is_slender'] else 'SHORT COLUMN'}",
    ]

    if slend["is_slender"]:
        lines.extend([
            f"   - Magnification Factor (delta_ns)= {slend['delta_ns']:.3f}",
            f"   - Design Magnified Moment (Mc)  = {slend['Mc'] / 1000.0:.2f} ton-m",
        ])
    else:
        lines.append(f"   - Design Moment (Mc = M2)       = {slend['Mc'] / 1000.0:.2f} ton-m")

    lines.extend([
        "-" * 78,
        "3. SHEAR & TIE DETAILING CHECK (ACI 318-14 Sec 22.5 & 25.7)",
        f"   - Factored Shear Demand (Vu)   = {slend['Vu'] / 1000.0:.2f} ton",
        f"   - Concrete Shear Capacity (φVc)= {(0.75 * slend['Vc']) / 1000.0:.2f} ton",
        f"   - Tie Shear Capacity (φVs)     = {(0.75 * slend['Vs']) / 1000.0:.2f} ton",
        f"   - Total Shear Strength (φVn)   = {slend['phi_Vn'] / 1000.0:.2f} ton",
        f"   - Shear D/C Ratio              = {slend['shear_dc_ratio']:.3f} [{slend['shear_status']}]",
        f"   - Provided Tie Spacing         = {data.tie_data.spacing:.1f} cm (Max Allow = {slend['tie_check']['max_allow_s']:.1f} cm) [{slend['tie_check']['status']}]",
        "-" * 78,
        "4. CAPACITY & SAFETY VERIFICATION SUMMARY",
        f"   - Pure Compression Cap (φPn,max)= {diagram['phi_Pn_max'] / 1000.0:.2f} ton",
        f"   - Design Axial Demand (Pu)     = {slend['Pu'] / 1000.0:.2f} ton",
        f"   - Bending Moment Demand (Mc)   = {slend['Mc'] / 1000.0:.2f} ton-m",
        f"   - Bending Moment Capacity (φMn)= {safety['phi_Mn_cap'] / 1000.0:.2f} ton-m",
        f"   - Overall Utilization Ratio(D/C)= {safety['dc_ratio']:.3f}",
        f"   - OVERALL DESIGN VERdict       = *** [{safety['status']}] ***",
        "=" * 78,
    ])

    return "\n".join(lines)