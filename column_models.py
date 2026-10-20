# ==============================================================================
# column_models.py - Central Configuration & Data Transfer Objects (DTO)
# Powered by Pydantic (ACI 318-14 RC Column Analysis & Design)
# ==============================================================================


from typing import List, Optional
from pydantic import BaseModel, Field


# ------------------------------------------------------------------------------
# 1. UNIT CONVERSION SYSTEM
# ------------------------------------------------------------------------------
class UnitConverter:
    """Standard unit conversion utilities to internal base units:
    - Distance / Geometry: cm
    - Force: kg
    - Moment: kg-m or kg-cm
    """
    @staticmethod
    def to_cm(value: float, unit: str) -> float:
        unit = unit.lower().strip()
        if unit == "m": return value * 100.0
        if unit == "mm": return value / 10.0
        if unit == "in": return value * 2.54
        if unit == "cm": return value
        raise ValueError(f"Unsupported length unit: '{unit}'")

    @staticmethod
    def to_kg(value: float, unit: str) -> float:
        unit = unit.lower().strip()
        if unit in ["ton", "t"]: return value * 1000.0
        if unit == "kn": return value * 101.9716
        if unit == "kg": return value
        raise ValueError(f"Unsupported force unit: '{unit}'")

    @staticmethod
    def to_kg_m(value: float, unit: str) -> float:
        unit = unit.lower().strip()
        if unit in ["ton-m", "t-m"]: return value * 1000.0
        if unit == "kn-m": return value * 101.9716
        if unit == "kg-cm": return value / 100.0
        if unit == "kg-m": return value
        raise ValueError(f"Unsupported moment unit: '{unit}'")


# ------------------------------------------------------------------------------
# 2. REINFORCEMENT DATA MODELS
# ------------------------------------------------------------------------------
class RebarLayer(BaseModel):
    """Stores parameters for a single layer of longitudinal reinforcement bars."""
    dia: float = Field(..., description="Bar diameter in millimeters (mm).")
    qty: int = Field(..., description="Number of bars present in this layer.")
    clear_dist: float = Field(0.0, description="Clear distance from adjacent layer in centimeters (cm).")


class TieDetail(BaseModel):
    """Stores column tie/stirrup detailing parameters."""
    tie_dia: float = Field(..., description="Tie bar diameter in millimeters (mm).")
    spacing: float = Field(..., description="Tie spacing in centimeters (cm).")
    legs: int = Field(2, description="Number of tie legs in section cross-direction.")


# ------------------------------------------------------------------------------
# 3. STRUCTURAL FORCES MODEL
# ------------------------------------------------------------------------------
class ColumnForces(BaseModel):
    """Stores ultimate design loads acting on the column (ULS Factored Forces)."""
    Pu: float = Field(0.0, description="Axial load in kg or ton (Positive = Compression).")
    Mu_top: float = Field(0.0, description="Bending moment at top section in kg-m or ton-m.")
    Mu_bot: float = Field(0.0, description="Bending moment at bottom section in kg-m or ton-m.")
    Vu: float = Field(0.0, description="Shear force in kg or ton.")


# ------------------------------------------------------------------------------
# 4. MASTER COLUMN INPUT DATA MODEL (Single Source of Truth)
# ------------------------------------------------------------------------------
class ColumnInputData(BaseModel):
    """Master data model holding complete column geometry, materials, and loadings."""
    # Material Strengths
    fc_prime: float = Field(..., description="Concrete compressive strength f'c (kg/cm2 / ksc).")
    fy: float = Field(..., description="Main longitudinal rebar yield strength fy (ksc).")
    fyt: float = Field(..., description="Tie rebar yield strength fyt (ksc).")
    
    # Section Geometry
    b: float = Field(..., description="Column section width in centimeters (cm).")
    h: float = Field(..., description="Column section depth in centimeters (cm).")
    covering: float = Field(4.0, description="Concrete clear cover to ties in centimeters (cm).")
    
    # Slenderness & Sway Parameters
    Lu: float = Field(0.0, description="Unsupported column height in meters (m).")
    K_x: float = Field(1.0, description="Effective length factor K in X-axis.")
    K_y: float = Field(1.0, description="Effective length factor K in Y-axis.")
    is_sway: bool = Field(False, description="Sway frame status (True = Sway, False = Non-Sway).")

    # Rebar Layouts
    top_rebars: list[RebarLayer] = Field(default_factory=list, description="Rebars at top/tension face.")
    bot_rebars: list[RebarLayer] = Field(default_factory=list, description="Rebars at bottom/compression face.")
    side_rebars: list[RebarLayer] = Field(default_factory=list, description="Side/web rebars.")
    tie_data: TieDetail = Field(..., description="Tie detailing specifications.")

    # Design Load Combination
    forces: ColumnForces = Field(..., description="Design forces envelope on column.")