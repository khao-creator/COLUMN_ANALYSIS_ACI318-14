# ==============================================================================
# main_gui.py - Integrated 3D RC Column Studio (PySide6 + PyVista + Matplotlib)
# Features: Real-time Input Forms, 3D Concrete & Rebar Viewport, 2D P-M Curves
# ==============================================================================

import math
import os
import sys

os.environ["QT_API"] = "pyside6"

import pyvista as pv
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from PySide6 import QtCore, QtGui, QtWidgets
from pyvistaqt import QtInteractor

from column_engine import run_full_column_analysis
from column_models import ColumnForces, ColumnInputData, RebarLayer, TieDetail
from column_reporter import (
    generate_text_report,
    plot_column_section,
    plot_interaction_diagram,
)


# ------------------------------------------------------------------------------
# 1. NUMERIC DELEGATE FOR INPUT VALIDATION
# ------------------------------------------------------------------------------
class FloatDelegate(QtWidgets.QStyledItemDelegate):
    """Validates double input fields to allow strictly numerical entries."""
    def createEditor(self, parent, option, index):
        editor = QtWidgets.QLineEdit(parent)
        validator = QtGui.QDoubleValidator(0.0, 1e9, 4, editor)
        validator.setNotation(QtGui.QDoubleValidator.Notation.StandardNotation)
        editor.setValidator(validator)
        editor.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        return editor


# ------------------------------------------------------------------------------
# 2. MAIN APPLICATION WINDOW
# ------------------------------------------------------------------------------
class ColumnStudioApp(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RC Column Studio - [ACI 318-14 Design Engine]")
        self.suppress_slenderness_warning = False
        self.resize(1400, 850)
        self.setMinimumSize(1000, 650)
        self._setup_ui()
        self.load_preset_on_startup()
        self.run_analysis_pipeline()

    # --------------------------------------------------------------------------
    # UI SETUP & LAYOUT INITIALIZATION
    # --------------------------------------------------------------------------
    def _setup_ui(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #0f172a; }
            QWidget#centralWidget { background-color: #0f172a; }
            QGroupBox {
                font-family: 'Segoe UI', sans-serif;
                font-size: 11px;
                font-weight: bold;
                color: #38bdf8;
                border: 1px solid #334155;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 10px;
                background-color: #1e293b;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
            QLabel { font-family: 'Segoe UI', sans-serif; font-size: 11px; color: #94a3b8; }
            QLineEdit {
                padding: 4px;
                border: 1px solid #475569;
                border-radius: 4px;
                background-color: #0f172a;
                color: #f8fafc;
                font-size: 11px;
            }
            QLineEdit:focus { border: 1.5px solid #0284c7; }
            QPushButton {
                font-family: 'Segoe UI', sans-serif;
                font-size: 11px;
                font-weight: bold;
                padding: 8px 14px;
                border-radius: 5px;
                background-color: #0284c7;
                color: #ffffff;
                border: none;
            }
            QPushButton:hover { background-color: #0369a1; }
            QPushButton:pressed { background-color: #075985; }
            QTabWidget::pane { border: 1px solid #334155; background-color: #1e293b; }
            QTabBar::tab {
                background: #0f172a;
                color: #94a3b8;
                padding: 8px 18px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-weight: bold;
                font-size: 11px;
            }
            QTabBar::tab:selected { background: #1e293b; color: #38bdf8; border-top: 2px solid #0284c7; }
            QTextEdit {
                background-color: #090d16;
                color: #38bdf8;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11px;
                border: 1px solid #334155;
            }
        """)

        central_widget = QtWidgets.QWidget(self)
        central_widget.setObjectName("centralWidget")
        self.setCentralWidget(central_widget)

        main_layout = QtWidgets.QHBoxLayout(central_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # ----------------------------------------------------------------------
        # LEFT CONTROL PANEL (INPUT FORMS)
        # ----------------------------------------------------------------------
        left_scroll = QtWidgets.QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFixedWidth(380)
        left_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)

        left_widget = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 4, 0)
        left_layout.setSpacing(6)

        # Group 1: Geometry & Materials
        grp_geom = QtWidgets.QGroupBox(" Geometry & Material Strength ")
        grid_geom = QtWidgets.QGridLayout(grp_geom)

        self.txt_b = self._create_input_field(grid_geom, "Width, b (cm):", "40.0", 0)
        self.txt_h = self._create_input_field(grid_geom, "Depth, h (cm):", "50.0", 1)
        self.txt_cov = self._create_input_field(grid_geom, "Covering (cm):", "4.0", 2)
        self.txt_fc = self._create_input_field(grid_geom, "Concrete f'c (ksc):", "280.0", 3)
        self.txt_fy = self._create_input_field(grid_geom, "Main Rebar fy (ksc):", "4000.0", 4)
        self.txt_fyt = self._create_input_field(grid_geom, "Tie Rebar fyt (ksc):", "2400.0", 5)

        left_layout.addWidget(grp_geom)

        # Group 2: Rebar Layout Configuration
        grp_rebar = QtWidgets.QGroupBox(" Reinforcement Layout ")
        grid_rebar = QtWidgets.QGridLayout(grp_rebar)

        self.txt_top_qty = self._create_input_field(grid_rebar, "Top Rebars (Qty):", "4", 0)
        self.txt_top_dia = self._create_input_field(grid_rebar, "Top Dia (mm):", "20.0", 1)
        self.txt_bot_qty = self._create_input_field(grid_rebar, "Bot Rebars (Qty):", "4", 2)
        self.txt_bot_dia = self._create_input_field(grid_rebar, "Bot Dia (mm):", "20.0", 3)
        self.txt_tie_dia = self._create_input_field(grid_rebar, "Tie Dia (mm):", "9.0", 4)
        self.txt_tie_spacing = self._create_input_field(grid_rebar, "Tie Spacing (cm):", "20.0", 5)

        left_layout.addWidget(grp_rebar)

        # Group 3: Design Forces & Slenderness
        grp_forces = QtWidgets.QGroupBox(" Factored Loads & Slenderness ")
        grid_forces = QtWidgets.QGridLayout(grp_forces)

        self.txt_Pu = self._create_input_field(grid_forces, "Axial Load Pu (kg):", "150000.0", 0)
        self.txt_Mu_top = self._create_input_field(grid_forces, "Mu Top (kg-m):", "12000.0", 1)
        self.txt_Mu_bot = self._create_input_field(grid_forces, "Mu Bot (kg-m):", "8000.0", 2)
        self.txt_Vu = self._create_input_field(grid_forces, "Shear Vu (kg):", "15000.0", 3)
        self.txt_Lu = self._create_input_field(grid_forces, "Length Lu (m):", "3.5", 4)
        self.txt_K = self._create_input_field(grid_forces, "Effective K Factor:", "1.0", 5)

        self.chk_sway = QtWidgets.QCheckBox("Sway Frame Condition")
        self.chk_sway.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: bold;")
        grid_forces.addWidget(self.chk_sway, 6, 0, 1, 2)

        left_layout.addWidget(grp_forces)

        # Action Buttons
        lay_btns = QtWidgets.QHBoxLayout()
        self.btn_run = QtWidgets.QPushButton("RUN ANALYSIS")
        self.btn_save_preset = QtWidgets.QPushButton("SAVE PRESET")
        self.btn_save_preset.setStyleSheet("""
            QPushButton {
                background-color: #059669;
            }
            QPushButton:hover { background-color: #047857; }
            QPushButton:pressed { background-color: #065f46; }
        """)

        self.btn_run.clicked.connect(self.run_analysis_pipeline)
        self.btn_save_preset.clicked.connect(self.save_preset)

        lay_btns.addWidget(self.btn_run)
        lay_btns.addWidget(self.btn_save_preset)
        left_layout.addLayout(lay_btns)

        left_layout.addStretch()
        left_scroll.setWidget(left_widget)
        main_layout.addWidget(left_scroll)

        # ----------------------------------------------------------------------
        # RIGHT DISPLAY PANEL (3D VIEWPORT / 2D CHARTS / PROOF SHEET)
        # ----------------------------------------------------------------------
        right_tab = QtWidgets.QTabWidget()

        # Tab 1: 3D CAD Viewport
        tab_3d = QtWidgets.QWidget()
        lay_3d = QtWidgets.QVBoxLayout(tab_3d)
        lay_3d.setContentsMargins(2, 2, 2, 2)
        lay_3d.setSpacing(4)

        # ── 3D Viewport Quick Toolbar ──
        lay_3d_tb = QtWidgets.QHBoxLayout()
        lay_3d_tb.setContentsMargins(4, 2, 4, 2)
        lay_3d_tb.setSpacing(6)

        btn_iso = QtWidgets.QPushButton("ISO")
        btn_front = QtWidgets.QPushButton("Front")
        btn_side = QtWidgets.QPushButton("Side")
        btn_top = QtWidgets.QPushButton("Top")
        btn_fit = QtWidgets.QPushButton("Fit View")

        for btn in (btn_iso, btn_front, btn_side, btn_top, btn_fit):
            btn.setStyleSheet("""
                QPushButton {
                    padding: 4px 10px;
                    font-size: 11px;
                    background-color: #334155;
                    border: 1px solid #475569;
                }
                QPushButton:hover { background-color: #0284c7; }
                QPushButton:pressed { background-color: #075985; }
            """)
            lay_3d_tb.addWidget(btn)

        lay_3d_tb.addStretch()

        # ── Toggle Checkbox for 3D Moment Vectors ──
        self.chk_show_moments = QtWidgets.QCheckBox("Show 3D Moments")
        self.chk_show_moments.setChecked(True)
        self.chk_show_moments.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: bold;")
        self.chk_show_moments.stateChanged.connect(lambda: self.run_analysis_pipeline())
        lay_3d_tb.addWidget(self.chk_show_moments)

        btn_iso.clicked.connect(self._set_view_iso)
        btn_front.clicked.connect(self._set_view_front)
        btn_side.clicked.connect(self._set_view_side)
        btn_top.clicked.connect(self._set_view_top)
        btn_fit.clicked.connect(self._fit_view)

        lay_3d.addLayout(lay_3d_tb)

        self.vtk_widget = QtInteractor(tab_3d)
        lay_3d.addWidget(self.vtk_widget)
        right_tab.addTab(tab_3d, " 3D CAD Viewport ")

        # ── CAD Centered Camera State & Interactor Setup ──────────────────
        interactor_widget = getattr(self.vtk_widget, "interactor", self.vtk_widget)
        if hasattr(interactor_widget, "SetInteractorStyle"):
            interactor_widget.SetInteractorStyle(None)

        self.cam_azim: float = -58.0
        self.cam_elev: float = 22.0
        self.cam_parallel_scale: float = 120.0
        self.pan_x: float = 0.0
        self.pan_y: float = 0.0
        self.cam_dist: float = 500.0

        self._drag_start: tuple[float, float] = (0.0, 0.0)
        self._drag_cam0: tuple[float, float] = (-58.0, 22.0)
        self._drag_pan0: tuple[float, float] = (0.0, 0.0)
        self._drag_mode: str | None = None
        self._drag_moved: bool = False
        self._DRAG_THRESHOLD_PX: float = 4.0

        self._PS_MIN: float = 1.0
        self._PS_MAX: float = 2000.0

        # Bind event listeners
        interactor_widget.mousePressEvent   = self._on_viewport_mouse_press
        interactor_widget.mouseMoveEvent    = self._on_viewport_mouse_move
        interactor_widget.mouseReleaseEvent = self._on_viewport_mouse_release
        interactor_widget.mouseDoubleClickEvent = lambda e: self._fit_view()
        interactor_widget.wheelEvent        = self._on_viewport_wheel

        # Tab 2: 2D Section & P-M Interaction Diagram
        tab_2d = QtWidgets.QWidget()
        self.lay_2d = QtWidgets.QHBoxLayout(tab_2d)
        self.lay_2d.setContentsMargins(4, 4, 4, 4)
        right_tab.addTab(tab_2d, " 2D Section & P-M Diagram ")

        # Tab 3: Text Mathematical Proof Sheet
        tab_proof = QtWidgets.QWidget()
        lay_proof = QtWidgets.QVBoxLayout(tab_proof)
        lay_proof.setContentsMargins(4, 4, 4, 4)
        self.txt_proof = QtWidgets.QTextEdit()
        self.txt_proof.setReadOnly(True)
        lay_proof.addWidget(self.txt_proof)
        right_tab.addTab(tab_proof, " Calculation Proof Sheet ")

        main_layout.addWidget(right_tab)

    # --------------------------------------------------------------------------
    # 3D CAD NAVIGATION ENGINE (MODEL CENTROID PIVOT & TURNTABLE ORBIT)
    # --------------------------------------------------------------------------
    _ORBIT_DEG_PER_PX: float = 0.35
    _ELEV_CLAMP: float = 84.0
    _ZOOM_STEP: float = 0.12
    
    def _show_slenderness_warning_dialog(self, warning_msg: str) -> None:
        """Show a slender warning pop-up with the option to turn off notifications in this session."""
        msg_box = QtWidgets.QMessageBox(self)
        msg_box.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        msg_box.setWindowTitle("Slenderness Warning")
        msg_box.setText("Slenderness Analysis Warning:")
        msg_box.setInformativeText(warning_msg)

        cb = QtWidgets.QCheckBox("Don't show this warning again in this session", msg_box)
        msg_box.setCheckBox(cb)

        msg_box.exec()

        if cb.isChecked():
            self.suppress_slenderness_warning = True

    # ── Camera View Presets ──────────────────────────────────────────────
    def _set_view_iso(self):
        """Switch to 3D Isometric View."""
        self.cam_azim = -58.0
        self.cam_elev = 22.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._apply_camera()

    def _set_view_front(self):
        """Switch to Front Elevation View (XZ)."""
        self.cam_azim = 0.0
        self.cam_elev = 0.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._apply_camera()

    def _set_view_side(self):
        """Switch to Side Elevation View (YZ)."""
        self.cam_azim = 90.0
        self.cam_elev = 0.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._apply_camera()

    def _set_view_top(self):
        """Switch to Top Plan View."""
        self.cam_azim = 0.0
        self.cam_elev = 88.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._apply_camera()

    # ── Camera View Presets (Z-Up Column Standing Orientation) ──────────
    def _set_view_iso(self):
        """Switch to 3D Isometric View (Column Standing Upright with proper pitch)."""
        self.cam_azim = -55.0
        self.cam_elev = 30.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._apply_camera()

    def _set_view_front(self):
        """Switch to Front Elevation View (XZ Plane)."""
        self.cam_azim = 0.0
        self.cam_elev = 0.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._apply_camera()

    def _set_view_side(self):
        """Switch to Side Elevation View (YZ Plane)."""
        self.cam_azim = 90.0
        self.cam_elev = 0.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._apply_camera()

    def _set_view_top(self):
        """Switch to Top Plan View (XY Plane looking down Z)."""
        self.cam_azim = 0.0
        self.cam_elev = 89.9
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._apply_camera()

    def _get_model_center(self) -> tuple[float, float, float]:
        """Compute the centroid of the column model."""
        Lu_cm = getattr(self, "current_column_Lu_cm", 200.0)
        return (0.0, 0.0, Lu_cm / 2.0)

    def _apply_camera(self) -> None:
        """Compute camera position and focal point with Z-Up Orientation for Column."""
        ra = math.radians(self.cam_azim)
        re = math.radians(self.cam_elev)

        cx, cy, cz = self._get_model_center()

        # Direction vector from focal point to camera eye (Z-Up Spherical Coordinates)
        dir_x = math.cos(re) * math.sin(ra)
        dir_y = -math.cos(re) * math.cos(ra)
        dir_z = math.sin(re)

        # Use Z-Up for standing column, switch to Y-Up for Top Plan View
        if abs(self.cam_elev) >= 88.0:
            up_x, up_y, up_z = (0.0, 1.0, 0.0)
        else:
            up_x, up_y, up_z = (0.0, 0.0, 1.0)

        # Screen Right unit vector
        rx = dir_y * up_z - dir_z * up_y
        ry = dir_z * up_x - dir_x * up_z
        rz = dir_x * up_y - dir_y * up_x
        r_mag = math.hypot(rx, ry, rz)
        if r_mag > 1e-6:
            rx /= r_mag
            ry /= r_mag
            rz /= r_mag

        # Screen Up unit vector
        vx = ry * dir_z - rz * dir_y
        vy = rz * dir_x - rx * dir_z
        vz = rx * dir_y - ry * dir_x
        v_mag = math.hypot(vx, vy, vz)
        if v_mag > 1e-6:
            vx /= v_mag
            vy /= v_mag
            vz /= v_mag

        # Screen-space pan offset applied relative to model centroid
        focal_x = cx - (self.pan_x * rx + self.pan_y * vx)
        focal_y = cy - (self.pan_x * ry + self.pan_y * vy)
        focal_z = cz - (self.pan_x * rz + self.pan_y * vz)

        eye_x = focal_x - self.cam_dist * dir_x
        eye_y = focal_y - self.cam_dist * dir_y
        eye_z = focal_z - self.cam_dist * dir_z

        self.vtk_widget.camera.position = (eye_x, eye_y, eye_z)
        self.vtk_widget.camera.focal_point = (focal_x, focal_y, focal_z)
        self.vtk_widget.camera.up = (up_x, up_y, up_z)

        # Orthographic projection scale
        self.vtk_widget.camera.parallel_projection = True
        self.vtk_widget.camera.parallel_scale = max(
            self._PS_MIN, min(self._PS_MAX, self.cam_parallel_scale)
        )

        self.vtk_widget.reset_camera_clipping_range()
        self.vtk_widget.render()

    def _fit_view(self) -> None:
        """Fit camera to encompass full column in 3D ISO Standing View."""
        Lu_cm = getattr(self, "current_column_Lu_cm", 200.0)
        b = getattr(self, "current_column_b", 40.0)
        h = getattr(self, "current_column_h", 50.0)
        span = max(b, h, Lu_cm / 2.0, 50.0)
        self.cam_azim = -45.0
        self.cam_elev = 25.0
        self.cam_dist = Lu_cm * 2.5 + 300.0
        self.cam_parallel_scale = span * 1.5
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._apply_camera()

    # ── Mouse Interaction Handlers ─────────────────────────────────────
    def _on_viewport_mouse_press(self, event: QtGui.QMouseEvent) -> None:
        """Dispatch drag mode: Left/Middle = Pan, Right = Orbit."""
        self._drag_start = (event.position().x(), event.position().y())
        self._drag_cam0 = (self.cam_azim, self.cam_elev)
        self._drag_pan0 = (self.pan_x, self.pan_y)
        self._drag_moved = False

        btn = event.button()
        mb = QtCore.Qt.MouseButton

        if btn in (mb.LeftButton, mb.MiddleButton):
            self._drag_mode = "pan"
        elif btn == mb.RightButton:
            self._drag_mode = "orbit"
        else:
            self._drag_mode = None

    def _on_viewport_mouse_move(self, event: QtGui.QMouseEvent) -> None:
        """Execute 1:1 Pan or Model-Centered Orbit."""
        if not self._drag_mode:
            return

        dx = event.position().x() - self._drag_start[0]
        dy = event.position().y() - self._drag_start[1]

        if not self._drag_moved:
            if math.hypot(dx, dy) < self._DRAG_THRESHOLD_PX:
                return
            self._drag_moved = True

        if self._drag_mode == "pan":
            interactor_widget = getattr(self.vtk_widget, "interactor", self.vtk_widget)
            widget_h = max(10, interactor_widget.height())
            meters_per_px = (2.0 * self.cam_parallel_scale) / widget_h
            self.pan_x = self._drag_pan0[0] + dx * meters_per_px
            self.pan_y = self._drag_pan0[1] - dy * meters_per_px
            self._apply_camera()

        elif self._drag_mode == "orbit":
            self.cam_azim = (
                self._drag_cam0[0] - dx * self._ORBIT_DEG_PER_PX + 180.0
            ) % 360.0 - 180.0
            self.cam_elev = max(
                -self._ELEV_CLAMP,
                min(self._ELEV_CLAMP, self._drag_cam0[1] + dy * self._ORBIT_DEG_PER_PX),
            )
            self._apply_camera()

    def _on_viewport_mouse_release(self, event: QtGui.QMouseEvent) -> None:
        self._drag_mode = None
        self._drag_moved = False

    def _on_viewport_wheel(self, event: QtGui.QWheelEvent) -> None:
        """Smooth cursor wheel zoom."""
        delta = event.angleDelta().y()
        if delta == 0:
            event.accept()
            return

        step = self._ZOOM_STEP
        if delta > 0:
            new_scale = self.cam_parallel_scale * (1.0 - step)
        else:
            new_scale = self.cam_parallel_scale * (1.0 + step)

        self.cam_parallel_scale = max(self._PS_MIN, min(self._PS_MAX, new_scale))
        self._apply_camera()
        event.accept()

    def _create_input_field(self, layout, label_text, default_value, row):
        lbl = QtWidgets.QLabel(label_text)
        txt = QtWidgets.QLineEdit(default_value)
        txt.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        layout.addWidget(lbl, row, 0)
        layout.addWidget(txt, row, 1)
        return txt

    # --------------------------------------------------------------------------
    # PRESET MANAGEMENT ENGINE (AUTO-SAVE & AUTO-LOAD)
    # --------------------------------------------------------------------------
    def _populate_ui_from_data(self, data: ColumnInputData):
        """Populates UI line edits and checkboxes from a ColumnInputData instance."""
        self.txt_b.setText(str(data.b))
        self.txt_h.setText(str(data.h))
        self.txt_cov.setText(str(data.covering))
        self.txt_fc.setText(str(data.fc_prime))
        self.txt_fy.setText(str(data.fy))
        self.txt_fyt.setText(str(data.fyt))

        if data.top_rebars:
            self.txt_top_qty.setText(str(data.top_rebars[0].qty))
            self.txt_top_dia.setText(str(data.top_rebars[0].dia))

        if data.bot_rebars:
            self.txt_bot_qty.setText(str(data.bot_rebars[0].qty))
            self.txt_bot_dia.setText(str(data.bot_rebars[0].dia))

        if data.tie_data:
            self.txt_tie_dia.setText(str(data.tie_data.tie_dia))
            self.txt_tie_spacing.setText(str(data.tie_data.spacing))

        if data.forces:
            self.txt_Pu.setText(str(data.forces.Pu))
            self.txt_Mu_top.setText(str(data.forces.Mu_top))
            self.txt_Mu_bot.setText(str(data.forces.Mu_bot))
            self.txt_Vu.setText(str(data.forces.Vu))

        self.txt_Lu.setText(str(data.Lu))
        self.txt_K.setText(str(data.K_x))
        self.chk_sway.setChecked(data.is_sway)

    def save_preset(self):
        """Saves current GUI inputs to column_preset.json file."""
        try:
            data = self.collect_input_data()
            try:
                json_str = data.model_dump_json(indent=2)
            except AttributeError:
                json_str = data.json(indent=2)

            with open("column_preset.json", "w", encoding="utf-8") as f:
                f.write(json_str)

            QtWidgets.QMessageBox.information(
                self, "Preset Saved", "Saved parameters to column_preset.json successfully!"
            )
        except Exception as e:  # noqa: BLE001
            QtWidgets.QMessageBox.critical(self, "Preset Error", f"Failed to save preset:\n{e}")

    def load_preset_on_startup(self):
        """Loads column_preset.json if present on startup."""
        filepath = "column_preset.json"
        if not os.path.exists(filepath):
            return

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            try:
                preset_data = ColumnInputData.model_validate_json(content)
            except AttributeError:
                preset_data = ColumnInputData.parse_raw(content)

            self._populate_ui_from_data(preset_data)
        except Exception as e:  # noqa: BLE001
            print(f"[PRESET NOTICE] Could not load preset: {e}")

    # --------------------------------------------------------------------------
    # PRESET MANAGEMENT ENGINE (AUTO-SAVE & AUTO-LOAD)
    # --------------------------------------------------------------------------
    def _populate_ui_from_data(self, data: ColumnInputData):
        """Populates UI line edits and checkboxes from a ColumnInputData instance."""
        self.txt_b.setText(str(data.b))
        self.txt_h.setText(str(data.h))
        self.txt_cov.setText(str(data.covering))
        self.txt_fc.setText(str(data.fc_prime))
        self.txt_fy.setText(str(data.fy))
        self.txt_fyt.setText(str(data.fyt))

        if data.top_rebars:
            self.txt_top_qty.setText(str(data.top_rebars[0].qty))
            self.txt_top_dia.setText(str(data.top_rebars[0].dia))

        if data.bot_rebars:
            self.txt_bot_qty.setText(str(data.bot_rebars[0].qty))
            self.txt_bot_dia.setText(str(data.bot_rebars[0].dia))

        if data.tie_data:
            self.txt_tie_dia.setText(str(data.tie_data.tie_dia))
            self.txt_tie_spacing.setText(str(data.tie_data.spacing))

        if data.forces:
            self.txt_Pu.setText(str(data.forces.Pu))
            self.txt_Mu_top.setText(str(data.forces.Mu_top))
            self.txt_Mu_bot.setText(str(data.forces.Mu_bot))
            self.txt_Vu.setText(str(data.forces.Vu))

        self.txt_Lu.setText(str(data.Lu))
        self.txt_K.setText(str(data.K_x))
        self.chk_sway.setChecked(data.is_sway)

    def save_preset(self):  # noqa: F811
        """Saves current GUI inputs to column_preset.json file."""
        try:
            data = self.collect_input_data()
            try:
                json_str = data.model_dump_json(indent=2)
            except AttributeError:
                json_str = data.json(indent=2)

            with open("column_preset.json", "w", encoding="utf-8") as f:
                f.write(json_str)

            QtWidgets.QMessageBox.information(
                self, "Preset Saved", "Saved parameters to column_preset.json successfully!"
            )
        except Exception as e:  # noqa: BLE001
            QtWidgets.QMessageBox.critical(self, "Preset Error", f"Failed to save preset:\n{e}")

    def load_preset_on_startup(self):  # noqa: F811
        """Loads column_preset.json if present on startup."""
        filepath = "column_preset.json"
        if not os.path.exists(filepath):
            return

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            try:
                preset_data = ColumnInputData.model_validate_json(content)
            except AttributeError:
                preset_data = ColumnInputData.parse_raw(content)

            self._populate_ui_from_data(preset_data)
        except Exception as e:  # noqa: BLE001
            print(f"[PRESET NOTICE] Could not load preset: {e}")

    # --------------------------------------------------------------------------
    # INPUT DATA COMPILER & PIPELINE ORCHESTRATION
    # --------------------------------------------------------------------------
    def collect_input_data(self) -> ColumnInputData:
        top_rebar = RebarLayer(
            dia=float(self.txt_top_dia.text() or 20.0),
            qty=int(self.txt_top_qty.text() or 4),
            clear_dist=0.0
        )
        bot_rebar = RebarLayer(
            dia=float(self.txt_bot_dia.text() or 20.0),
            qty=int(self.txt_bot_qty.text() or 4),
            clear_dist=0.0
        )
        tie = TieDetail(
            tie_dia=float(self.txt_tie_dia.text() or 9.0),
            spacing=float(self.txt_tie_spacing.text() or 20.0),
            legs=2
        )
        forces = ColumnForces(
            Pu=float(self.txt_Pu.text() or 0.0),
            Mu_top=float(self.txt_Mu_top.text() or 0.0),
            Mu_bot=float(self.txt_Mu_bot.text() or 0.0),
            Vu=float(self.txt_Vu.text() or 0.0)
        )
        return ColumnInputData(
            fc_prime=float(self.txt_fc.text() or 280.0),
            fy=float(self.txt_fy.text() or 4000.0),
            fyt=float(self.txt_fyt.text() or 2400.0),
            b=float(self.txt_b.text() or 40.0),
            h=float(self.txt_h.text() or 50.0),
            covering=float(self.txt_cov.text() or 4.0),
            Lu=float(self.txt_Lu.text() or 3.5),
            K_x=float(self.txt_K.text() or 1.0),
            K_y=float(self.txt_K.text() or 1.0),
            is_sway=self.chk_sway.isChecked(),
            top_rebars=[top_rebar],
            bot_rebars=[bot_rebar],
            side_rebars=[],
            tie_data=tie,
            forces=forces
        )

    def run_analysis_pipeline(self):
        try:
            data = self.collect_input_data()
            results = run_full_column_analysis(data)

            # Verify slenderness warnings
            slenderness_data = results.get("slenderness_and_shear", {})
            warnings = slenderness_data.get("warnings", [])

            if warnings and not getattr(self, "suppress_slenderness_warning", False):
                self._show_slenderness_warning_dialog(warnings[0])

            self._update_3d_viewport(data, results)
            self._update_2d_plots(data, results)
            self._update_proof_sheet(data, results)

        except Exception as e:  # noqa: BLE001
            QtWidgets.QMessageBox.critical(self, "Analysis Error", f"Failed to execute analysis pipeline:\n{e}")

    # --------------------------------------------------------------------------
    # RENDERERS: 3D VIEWPORT, 2D CHARTS, PROOF SHEET
    # --------------------------------------------------------------------------
    def _update_3d_viewport(self, data: ColumnInputData, results: dict):
        self.vtk_widget.clear()
        self.vtk_widget.set_background("#090d16")

        b, h = data.b, data.h
        Lu_cm = data.Lu * 100.0 if data.Lu > 0 else 200.0

        # 1. Semi-transparent concrete column body
        concrete = pv.Cube(center=(0, 0, Lu_cm / 2.0), x_length=b, y_length=h, z_length=Lu_cm)
        self.vtk_widget.add_mesh(concrete, color="#cbd5e1", opacity=0.35, show_edges=True, edge_color="#475569")

        # 2. Longitudinal rebar cylinders
        rebars = results["section_properties"]["processed_rebars"]
        tie_w = b - 2.0 * data.covering
        tie_db_cm = data.tie_data.tie_dia / 10.0

        for layer in rebars:
            qty = layer["qty_i"]
            db_cm = layer["db_i"] / 10.0
            y_pos = layer["y_dist_i"]

            if qty == 1:
                x_positions = [0.0]
            else:
                x_start = -(tie_w / 2.0) + tie_db_cm + (db_cm / 2.0)
                x_end = (tie_w / 2.0) - tie_db_cm - (db_cm / 2.0)
                step = (x_end - x_start) / max(1, qty - 1)
                x_positions = [x_start + i * step for i in range(qty)]

            for x_pos in x_positions:
                bar = pv.Cylinder(center=(x_pos, -y_pos, Lu_cm / 2.0), direction=(0, 0, 1), radius=db_cm / 2.0, height=Lu_cm)
                self.vtk_widget.add_mesh(bar, color="#dc2626", metallic=0.5)

        # 3. Dynamic Bending Moment Visualizer (หมุนรอบแกน X สเกลสัมพันธ์กับหน้าตัดเสา)
        if getattr(self, "chk_show_moments", None) and self.chk_show_moments.isChecked():
            Mu_top = data.forces.Mu_top
            Mu_bot = data.forces.Mu_bot

            # คำนวณขนาดและระยะยื่นของวงโค้งสเกลตามหน้าตัดเสาจริง
            dim_max = max(b, h)
            arc_inner = dim_max * 0.65
            arc_outer = dim_max * 0.82
            cone_height = dim_max * 0.30
            cone_radius = dim_max * 0.10

            # ── Moment Top (Z = Lu_cm) ──
            if abs(Mu_top) > 0:
                top_color = "#ef4444" if Mu_top < 0 else "#38bdf8"
                # ตั้งระนาบวงโค้งให้ดัดรอบแกน X (normal = 1, 0, 0)
                top_arc = pv.Disc(center=(0, 0, Lu_cm), inner=arc_inner, outer=arc_outer, 
                                normal=(1, 0, 0), r_res=1, c_res=30)
                self.vtk_widget.add_mesh(top_arc, color=top_color, opacity=0.85)

                # หัวลูกศรโค้งตามทิศทางแรงดัด (Right-hand rule)
                dir_z = 1.0 if Mu_top > 0 else -1.0
                cone_top = pv.Cone(center=(0, arc_inner, Lu_cm), direction=(0, 0, dir_z), 
                                   height=cone_height, radius=cone_radius)
                self.vtk_widget.add_mesh(cone_top, color=top_color)

            # ── Moment Bottom (Z = 0) ──
            if abs(Mu_bot) > 0:
                bot_color = "#ef4444" if Mu_bot < 0 else "#38bdf8"
                # ตั้งระนาบวงโค้งให้ดัดรอบแกน X (normal = 1, 0, 0)
                bot_arc = pv.Disc(center=(0, 0, 0), inner=arc_inner, outer=arc_outer, 
                                normal=(1, 0, 0), r_res=1, c_res=30)
                self.vtk_widget.add_mesh(bot_arc, color=bot_color, opacity=0.85)

                # หัวลูกศรโค้งตามทิศทางแรงดัด
                dir_z = 1.0 if Mu_bot > 0 else -1.0
                cone_bot = pv.Cone(center=(0, arc_inner, 0), direction=(0, 0, dir_z), 
                                   height=cone_height, radius=cone_radius)
                self.vtk_widget.add_mesh(cone_bot, color=bot_color)

        if not hasattr(self, "_camera_initialized") or not self._camera_initialized:
            self.vtk_widget.add_axes(interactive=False, line_width=3, xlabel="X", ylabel="Y", zlabel="Z")
            self._fit_view()
            self._camera_initialized = True
        else:
            self._apply_camera()
    def _update_2d_plots(self, data: ColumnInputData, results: dict):
        # Clear existing 2D widgets
        while self.lay_2d.count():
            item = self.lay_2d.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        fig_sec = plot_column_section(data, results["section_properties"], results.get("slenderness_and_shear", {}))
        fig_pm = plot_interaction_diagram(results["interaction_diagram"], results["slenderness_and_shear"])

        canvas_sec = FigureCanvas(fig_sec)
        canvas_pm = FigureCanvas(fig_pm)

        self.lay_2d.addWidget(canvas_sec)
        self.lay_2d.addWidget(canvas_pm)

    def _update_proof_sheet(self, data: ColumnInputData, results: dict):
        report_str = generate_text_report(data, results)
        self.txt_proof.setText(report_str)

# ------------------------------------------------------------------------------
# APPLICATION ENTRY POINT
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = ColumnStudioApp()
    window.show()
    sys.exit(app.exec())