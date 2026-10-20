# ==============================================================================
# column_engine.py - Core Engineering & Analytical Engine (ACI 318-14)
# Contains: Section Properties, Slenderness Magnification, P-M Diagram Sweeper
# ==============================================================================

import math
from typing import Any, Dict, List  # noqa: UP035

from column_models import ColumnInputData, RebarLayer


# ------------------------------------------------------------------------------
# 1. SECTION PROPERTIES ENGINE (MODULE 2)
# ------------------------------------------------------------------------------
def compute_beta1(fc_prime: float) -> float:
    """
    Calculates ACI 318-14 Table 22.2.2.4.3 beta1 factor.
    fc_prime is in kg/cm² (ksc).
    """
    if fc_prime <= 280.0:
        return 0.85
    elif fc_prime >= 560.0:
        return 0.65
    else:
        return 0.85 - 0.05 * ((fc_prime - 280.0) / 70.0)


def calculate_column_section_properties(data: ColumnInputData) -> Dict[str, Any]:  # noqa: UP006
    """
    Calculates gross concrete section properties (Ag, Ig, r, yc) and processes 
    rebar coordinates relative to section centerline.
    """
    section_width = data.b
    section_depth = data.h

    Ag = section_width * section_depth
    Ig = (section_width * (section_depth ** 3)) / 12.0
    r = math.sqrt(Ig / Ag)
    yc = section_depth / 2.0

    Ast = 0.0
    total_bar_count = 0
    processed_rebars = []
    warnings = []

    tie_db_cm = data.tie_data.tie_dia / 10.0
    net_width = section_width - (2.0 * data.covering) - (2.0 * tie_db_cm)

    if net_width <= 0:
        warnings.append(f"[CRITICAL ERROR] Cover and ties exceed section width ({section_width} cm).")

    # Helper function to register rebar layers
    layer_counter = 1

    def add_layer_group(rebars: List[RebarLayer], default_depth_from_top: bool = True):  # noqa: UP006
        nonlocal Ast, total_bar_count, layer_counter
        for layer in rebars:
            if layer.qty <= 0 or layer.dia <= 0:
                continue

            db_cm = layer.dia / 10.0
            layer_area = layer.qty * (math.pi * (db_cm ** 2)) / 4.0
            Ast += layer_area
            total_bar_count += layer.qty

            # Determine depth from top concrete compression edge (d_i)
            d_i = layer.clear_dist if layer.clear_dist > 0 else (
                data.covering + tie_db_cm + (db_cm / 2.0) if default_depth_from_top 
                else section_depth - (data.covering + tie_db_cm + (db_cm / 2.0))
            )
            
            y_dist_i = d_i - yc

            processed_rebars.append({
                "layer_index": layer_counter,
                "As_i": round(layer_area, 4),
                "y_dist_i": round(y_dist_i, 3),
                "d_i": round(d_i, 3),
                "db_i": layer.dia,
                "qty_i": layer.qty
            })
            layer_counter += 1

    # Add Top, Bottom, and Side rebar groups
    add_layer_group(data.top_rebars, default_depth_from_top=True)
    add_layer_group(data.bot_rebars, default_depth_from_top=False)
    add_layer_group(data.side_rebars, default_depth_from_top=True)

    # Detailing & Reinforcement Ratio Verification
    rho_g = Ast / Ag if Ag > 0 else 0.0
    if rho_g < 0.01:
        warnings.append(f"[ACI WARNING] Reinforcement ratio rho_g ({rho_g*100:.2f}%) is below ACI minimum (1.00%).")
    elif rho_g > 0.08:
        warnings.append(f"[ACI WARNING] Reinforcement ratio rho_g ({rho_g*100:.2f}%) exceeds ACI maximum (8.00%).")

    if total_bar_count < 4:
        warnings.append(f"[DETAILING WARNING] Found {total_bar_count} bars. Minimum 4 bars required for tied columns.")

    return {
        "Ag": round(Ag, 2),
        "Ig": round(Ig, 2),
        "r": round(r, 3),
        "yc": round(yc, 2),
        "Ast": round(Ast, 3),
        "rho_g": round(rho_g, 5),
        "section_depth": section_depth,
        "section_width": section_width,
        "processed_rebars": processed_rebars,
        "warnings": warnings
    }


# ------------------------------------------------------------------------------
# 2. SLENDERNESS & SHEAR CAPACITY ENGINE (MODULE 3)
# ------------------------------------------------------------------------------
def run_slenderness_engine(data: ColumnInputData, props: Dict[str, Any]) -> Dict[str, Any]:  # noqa: UP006
    """
    Evaluates slenderness ratio, computes moment magnification factor (Mc),
    and verifies shear capacity (ACI 318-14).
    """
    Pu = data.forces.Pu
    Mu_top = data.forces.Mu_top
    Mu_bot = data.forces.Mu_bot

    abs_top = abs(Mu_top)
    abs_bot = abs(Mu_bot)

    r = props["r"]
    h = props["section_depth"]
    Ig = props["Ig"]

    # Identify controlling moment M2 and M1
    if abs_top >= abs_bot:
        M2, M1 = abs_top, abs_bot
        critical_end = "Top"
    else:
        M2, M1 = abs_bot, abs_top
        critical_end = "Bottom"

    # Curvature Ratio (M1/M2) with ACI 318-14 sign convention
    if M2 > 0:
        ratio = M1 / M2
        ratio_signed = ratio if (Mu_top * Mu_bot < 0) else -ratio
    else:
        ratio_signed = 0.0

    K = max(data.K_x, data.K_y)
    Lu = data.Lu * 100.0  # Convert meters to cm

    # Slenderness Ratio & Limit Check (ACI 318-14 Sec 6.2.5)
    slenderness_ratio = (K * Lu) / r if r > 0 else 0.0

    if not data.is_sway:
        limit = min(40.0, 34.0 + (12.0 * ratio_signed))
    else:
        limit = 22.0

    is_slender = slenderness_ratio > limit

    # Shear Capacity Check (ACI 318-14 Sec 22.5.6.1 & Sec 22.5.7.1)
    b_w = props["section_width"]
    d_eff = max([layer["d_i"] for layer in props["processed_rebars"]], default=h - 6.0)
    Ag_sec = props["Ag"]

    if Pu >= 0:
        comp_mult = min(1.0 + (Pu / (140.0 * Ag_sec)), 1.5)
        Vc = 0.53 * comp_mult * math.sqrt(data.fc_prime) * b_w * d_eff
    else:
        Vc = max(0.0, 0.53 * (1.0 + (Pu / (35.0 * Ag_sec))) * math.sqrt(data.fc_prime) * b_w * d_eff)

    # Transverse tie shear capacity (Vs)
    tie_dia_cm = data.tie_data.tie_dia / 10.0
    Av = data.tie_data.legs * ((math.pi * (tie_dia_cm ** 2)) / 4.0)
    Vs = (Av * data.fyt * d_eff) / data.tie_data.spacing if data.tie_data.spacing > 0 else 0.0

    Vn = Vc + Vs
    phi_v = 0.75
    phi_Vn = phi_v * Vn
    shear_dc_ratio = abs(data.forces.Vu) / phi_Vn if phi_Vn > 0 else 0.0

    # Column Tie Detailing Check (ACI 318-14 Sec 25.7.2.1)
    min_main_db = min([layer["db_i"] for layer in props["processed_rebars"]], default=16.0)
    s_limit_16db = 16.0 * (min_main_db / 10.0)
    s_limit_48dt = 48.0 * tie_dia_cm
    s_limit_least_dim = min(data.b, data.h)
    s_tie_max_allow = min(s_limit_16db, s_limit_48dt, s_limit_least_dim)
    is_tie_spacing_safe = data.tie_data.spacing <= s_tie_max_allow

    base_output = {
        "critical_end": critical_end,
        "ratio_signed": round(ratio_signed, 3),
        "Pu": Pu,
        "Vu": data.forces.Vu,
        "Vc": round(Vc, 2),
        "Vs": round(Vs, 2),
        "phi_Vn": round(phi_Vn, 2),
        "shear_dc_ratio": round(shear_dc_ratio, 3),
        "shear_status": "PASS" if shear_dc_ratio <= 1.0 else "FAIL",
        "tie_check": {
            "provided_s": data.tie_data.spacing,
            "max_allow_s": round(s_tie_max_allow, 1),
            "status": "PASS" if is_tie_spacing_safe else "FAIL"
        }
    }

    # Slenderness Branching Logic
    if not is_slender:
        base_output.update({
            "is_slender": False,
            "slenderness_ratio": round(slenderness_ratio, 2),
            "limit": round(limit, 2),
            "M2_design": round(M2, 2),
            "Mc": round(M2, 2),
            "delta_ns": 1.0
        })
        return base_output
    else:
        M2_min = (Pu * (1.5 + 0.03 * h)) / 100.0  # kg-m
        M2_design = max(M2, M2_min)
        beta_dns = 0.5

        Ec = 15100.0 * math.sqrt(data.fc_prime)
        EI = (0.4 * Ec * Ig) / (1.0 + beta_dns)
        Pc = (math.pi ** 2 * EI) / ((K * Lu) ** 2) if (K * Lu) > 0 else 1e9

        if data.is_sway:
            Cm = 1.0  
        else:
            Cm = max(0.4, 0.6 + (0.4 * ratio_signed))  
        denom = 1.0 - (Pu / (0.75 * Pc))

        slenderness_warnings = []
        if denom <= 0:
            slenderness_warnings.append("[SLENDERNESS WARNING] Axial load Pu exceeds 0.75*Pc. Column will buckle!")
            delta_ns = 999.0
        else:
            delta_ns = max(1.0, Cm / denom)

        Mc = delta_ns * M2_design

        base_output.update({
            "is_slender": True,
            "slenderness_ratio": round(slenderness_ratio, 2),
            "limit": round(limit, 2),
            "M2_min": round(M2_min, 2),
            "M2_design": round(M2_design, 2),
            "delta_ns": round(delta_ns, 3),
            "Mc": round(Mc, 2),
            "Pc": round(Pc, 2),
            "Ec": round(Ec, 2),
            "EI": round(EI, 2),
            "warnings": slenderness_warnings
        })
        return base_output

# ------------------------------------------------------------------------------
# 3. INTERACTION DIAGRAM ENGINE (MODULE 4)
# ------------------------------------------------------------------------------
def evaluate_section_at_c(c: float, data: ColumnInputData, props: Dict[str, Any]) -> Dict[str, Any]:  # noqa: UP006
    """Evaluates nominal and design axial-moment capacity for a given neutral axis depth c."""
    Es = 2.04e6
    fc_prime = data.fc_prime
    fy = data.fy

    b = props["section_width"]
    h = props["section_depth"]
    yc = props["yc"]
    rebars = props["processed_rebars"]

    beta1 = compute_beta1(fc_prime)
    a = min(beta1 * c, h)

    Cc = 0.85 * fc_prime * a * b
    Mn_concrete = Cc * (yc - (a / 2.0))

    sum_Fs = 0.0
    sum_Ms = 0.0
    dt = max([r["d_i"] for r in rebars], default=h - 6.0)

    for layer in rebars:
        d_i = layer["d_i"]
        As_i = layer["As_i"]
        y_dist_i = layer["y_dist_i"]

        eps_si = 0.003 * ((c - d_i) / c) if c > 0 else -0.003
        f_si = max(-fy, min(fy, Es * eps_si))

        if d_i <= a and f_si > 0:
            f_net = f_si - (0.85 * fc_prime)
        else:
            f_net = f_si

        F_si = As_i * f_net
        sum_Fs += F_si
        sum_Ms += (-F_si * y_dist_i)

    Pn = Cc + sum_Fs
    Mn = (Mn_concrete + sum_Ms) / 100.0  # Convert kg-cm to kg-m

    eps_t = 0.003 * ((dt - c) / c) if c > 0 else 0.005
    eps_ty = fy / Es

    # ACI 318-14 Strength Reduction Factor Transition
    if eps_t <= eps_ty:
        phi = 0.65
    elif eps_t >= 0.005:
        phi = 0.90
    else:
        phi = 0.65 + 0.25 * ((eps_t - eps_ty) / (0.005 - eps_ty))
        phi = max(0.65, min(0.90, phi))

    return {
        "c": c,
        "Pn": Pn,
        "Mn": Mn,
        "phi": round(phi, 4),
        "phi_Pn": phi * Pn,
        "phi_Mn": phi * Mn,
        "eps_t": eps_t
    }


def generate_interaction_diagram(data: ColumnInputData, props: Dict[str, Any], num_points: int = 80) -> Dict[str, Any]:  # noqa: UP006
    """Sweeps neutral axis 'c' to build nominal and design P-M interaction curves."""
    fc_prime = data.fc_prime
    fy = data.fy
    Ag = props["Ag"]
    Ast = props["Ast"]
    h = props["section_depth"]

    # Boundary Capacities
    P0 = (0.85 * fc_prime * (Ag - Ast)) + (fy * Ast)
    phi_Pn_max = 0.80 * 0.65 * P0
    
    Pnt = -fy * Ast
    phi_Pnt = -0.90 * fy * Ast

    c_max = 3.0 * h
    c_min = 0.05 * h

    nominal_curve = [{"Pn": P0, "Mn": 0.0}]
    design_curve = [{"phi_Pn": phi_Pn_max, "phi_Mn": 0.0}]

    for i in range(num_points):
        factor = (i / (num_points - 1)) ** 1.5
        c = c_max - factor * (c_max - c_min)
        point = evaluate_section_at_c(c, data, props)

        nominal_curve.append({"Pn": point["Pn"], "Mn": point["Mn"]})
        phi_Pn_capped = min(point["phi_Pn"], phi_Pn_max)
        design_curve.append({"phi_Pn": phi_Pn_capped, "phi_Mn": point["phi_Mn"]})

    nominal_curve.append({"Pn": Pnt, "Mn": 0.0})
    design_curve.append({"phi_Pn": phi_Pnt, "phi_Mn": 0.0})

    return {
        "P0": round(P0, 2),
        "phi_Pn_max": round(phi_Pn_max, 2),
        "Pnt": round(Pnt, 2),
        "phi_Pnt": round(phi_Pnt, 2),
        "nominal_curve": nominal_curve,
        "design_curve": design_curve
    }


def verify_demand_safety(demand: Dict[str, Any], diagram: Dict[str, Any]) -> Dict[str, Any]:  # noqa: UP006
    """Verifies whether (Pu, Mc) demand lies inside design curve and calculates D/C ratio."""
    Pu = demand["Pu"]
    Mc = demand["Mc"]
    
    phi_Pn_max = diagram["phi_Pn_max"]
    phi_Pnt = diagram["phi_Pnt"]
    des_curve = diagram["design_curve"]

    if Pu > phi_Pn_max:
        return {
            "status": "FAIL",
            "dc_ratio": round(Pu / phi_Pn_max, 3),
            "phi_Mn_cap": 0.0,
            "message": f"Axial load Pu ({Pu:.0f} kg) exceeds maximum cap phi*Pn,max ({phi_Pn_max:.0f} kg)."
        }
    if Pu < phi_Pnt:
        return {
            "status": "FAIL",
            "dc_ratio": round(abs(Pu) / abs(phi_Pnt), 3),
            "phi_Mn_cap": 0.0,
            "message": "Tensile load exceeds pure tension capacity."
        }

    phi_Mn_cap = 0.0
    for i in range(len(des_curve) - 1):
        p1, p2 = des_curve[i]["phi_Pn"], des_curve[i + 1]["phi_Pn"]
        m1, m2 = des_curve[i]["phi_Mn"], des_curve[i + 1]["phi_Mn"]

        if (p1 >= Pu >= p2) or (p2 >= Pu >= p1):
            if abs(p1 - p2) > 1e-5:
                t = (Pu - p2) / (p1 - p2)
                phi_Mn_cap = m2 + t * (m1 - m2)
            else:
                phi_Mn_cap = max(m1, m2)
            break

    dc_ratio = (Mc / phi_Mn_cap) if phi_Mn_cap > 0 else (0.0 if Mc == 0 else 999.0)
    status = "PASS" if dc_ratio <= 1.0 else "FAIL"

    return {
        "status": status,
        "dc_ratio": round(dc_ratio, 3),
        "phi_Mn_cap": round(phi_Mn_cap, 2),
        "message": f"D/C Ratio = {dc_ratio:.3f} ({status})"
    }


# ------------------------------------------------------------------------------
# 4. MASTER ANALYSIS ORCHESTRATOR (MODULE 5)
# ------------------------------------------------------------------------------
def run_full_column_analysis(input_data: ColumnInputData) -> dict[str, Any]:
    """Runs full column evaluation pipeline from geometry to safety verification."""
    props = calculate_column_section_properties(input_data)
    slenderness_and_shear = run_slenderness_engine(input_data, props)
    diagram = generate_interaction_diagram(input_data, props)
    safety = verify_demand_safety(slenderness_and_shear, diagram)

    return {
        "section_properties": props,
        "slenderness_and_shear": slenderness_and_shear,
        "interaction_diagram": diagram,
        "safety_verification": safety
    }