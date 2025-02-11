import tkinter as tk
from tkinter import ttk, messagebox
import time
import pygame
import win32api
import win32con

# -----------------------------
# Helper function: Send key
# -----------------------------
def send_key(vk_code):
    """Simulate a key press and release on Windows."""
    win32api.keybd_event(vk_code, 0, 0, 0)      # key down
    win32api.keybd_event(vk_code, 0, win32con.KEYEVENTF_KEYUP, 0)  # key up
    print(f"Sent key: {vk_code:#04x}")

# -----------------------------
# Main Application Class
# -----------------------------
class SimMusicSwitcher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Sim music switcher")
        self.geometry("700x450")
        
        # Initialize pygame and the joystick subsystem
        pygame.init()
        pygame.joystick.init()
        self.joystick = None

        # --- Mapping Variables ---
        # mapping: action_name -> mapping info
        # For a toggle action, mapping info is a dict:
        #    { "input_type": "axis" or "button", "index": int }
        self.mapping = {}
        # For each action, track its last logical state for edge detection.
        self.action_last_state = {}
        # When assigning an action, record the baseline state of every control
        # so that only a genuine "flip" (a change from baseline) is accepted.
        self.assignment_start_state = {}

        # Polling settings
        self.poll_interval = 50  # ms between polls
        # A control is considered "active" if its value > toggle_threshold.
        # (Threshold is adjusted based on radio type below.)
        self.toggle_threshold = 0.8  # default for FrSky

        # --- Define Actions (only two now) ---
        # "Next Track" uses VK_MEDIA_NEXT_TRACK (0xB0)
        # "Previous Track" uses VK_MEDIA_PREV_TRACK (0xB1)
        self.actions = [
            {"name": "Next Track", "vk": 0xB0},
            {"name": "Previous Track", "vk": 0xB1}
        ]
        
        # Monitoring flag (auto-monitoring always runs when not assigning)
        self.monitoring = True

        # --- Radio Type (FrSky or SquidStick) ---
        self.radio_type = tk.StringVar(value="FrSky")

        # To avoid conflicts with tkinter internals, use a name less likely to conflict.
        self._current_assignment_action = None

        # Build the GUI, set up the joystick, and start auto-monitoring.
        self.create_widgets()
        self.setup_joystick()
        self.monitor_loop()  # start auto-monitoring

    def create_widgets(self):
        # --- Top Frame: Radio Type & Device Info ---
        top_frame = ttk.LabelFrame(self, text="Device & Radio Type", padding=10)
        top_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(top_frame, text="Radio Type:").grid(row=0, column=0, sticky="w")
        self.radio_menu = ttk.Combobox(top_frame, textvariable=self.radio_type, state="readonly",
                                       values=["FrSky", "SquidStick"])
        self.radio_menu.grid(row=0, column=1, padx=5, pady=5)
        self.radio_menu.bind("<<ComboboxSelected>>", self.on_radio_type_change)
        
        self.device_label = ttk.Label(top_frame, text="Device: (not found)")
        self.device_label.grid(row=0, column=2, padx=20)
        
        # --- Middle Frame: Logging & Action Mapping ---
        mid_frame = ttk.LabelFrame(self, text="Action Mapping", padding=10)
        mid_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.log_text = tk.Text(mid_frame, height=8)
        self.log_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.log("Using the first connected joystick for control assignments.")
        
        # Mapping table header
        table_frame = ttk.Frame(mid_frame)
        table_frame.pack(fill="x", padx=5, pady=5)
        ttk.Label(table_frame, text="Action", width=20, anchor="center").grid(row=0, column=0, padx=5)
        ttk.Label(table_frame, text="Mapping", width=20, anchor="center").grid(row=0, column=1, padx=5)
        ttk.Label(table_frame, text="Assign", width=10, anchor="center").grid(row=0, column=2, padx=5)
        
        # Create one row per action
        self.action_rows = {}
        for i, action in enumerate(self.actions, start=1):
            act_name = action["name"]
            ttk.Label(table_frame, text=act_name, width=20).grid(row=i, column=0, padx=5, pady=2)
            mapping_lbl = ttk.Label(table_frame, text="None", width=20)
            mapping_lbl.grid(row=i, column=1, padx=5, pady=2)
            btn = ttk.Button(table_frame, text="Assign", command=lambda a=act_name: self.start_assignment(a))
            btn.grid(row=i, column=2, padx=5, pady=2)
            self.action_rows[act_name] = {"label": mapping_lbl, "button": btn}
            self.mapping[act_name] = None
            self.action_last_state[act_name] = False

    def log(self, msg):
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        print(msg)

    def on_radio_type_change(self, event):
        rt = self.radio_type.get()
        if rt == "SquidStick":
            self.toggle_threshold = 0.9
        else:
            self.toggle_threshold = 0.8
        self.log(f"Radio type set to {rt}; toggle threshold = {self.toggle_threshold}")

    def setup_joystick(self):
        count = pygame.joystick.get_count()
        if count == 0:
            messagebox.showerror("Error", "No joystick device found!")
            self.device_label.config(text="Device: Not found")
            return
        # Use the first joystick.
        self.joystick = pygame.joystick.Joystick(0)
        self.joystick.init()
        dev_name = self.joystick.get_name()
        self.device_label.config(text=f"Device: {dev_name}")
        self.log(f"Using joystick: {dev_name}")

    # -----------------------------
    # Assignment Methods
    # -----------------------------
    def start_assignment(self, action_name):
        if self.joystick is None:
            messagebox.showerror("Error", "No joystick device found!")
            return
        self._current_assignment_action = action_name
        self.assignment_start_state = {}
        self.log(f"Assignment: Waiting 500ms to record baseline for '{action_name}'. Make sure the control is inactive.")
        self.after(500, self.record_assignment_baseline)

    def record_assignment_baseline(self):
        pygame.event.pump()
        # For buttons: record their boolean state (active if nonzero)
        for btn in range(self.joystick.get_numbuttons()):
            self.assignment_start_state[("button", btn)] = bool(self.joystick.get_button(btn))
        # For axes: record baseline as (value > 0)
        for axis in range(self.joystick.get_numaxes()):
            self.assignment_start_state[("axis", axis)] = (self.joystick.get_axis(axis) > 0)
        self.log("Baseline for assignment recorded. Now flip the desired control for assignment.")
        self.after(self.poll_interval, self.check_assignment_input)

    def check_assignment_input(self):
        if self._current_assignment_action is None:
            return
        pygame.event.pump()
        action = next((a for a in self.actions if a["name"] == self._current_assignment_action), None)
        if action is None:
            return
        # Check buttons first.
        for btn in range(self.joystick.get_numbuttons()):
            pygame.event.pump()
            baseline = self.assignment_start_state.get(("button", btn), True)
            current_state = bool(self.joystick.get_button(btn))
            if (not baseline) and current_state:
                self.mapping[action["name"]] = {"input_type": "button", "index": btn}
                self.action_rows[action["name"]]["label"].config(text=f"Button {btn}")
                self.log(f"Assigned '{action['name']}' to Button {btn}.")
                self._current_assignment_action = None
                return
        # Then check axes.
        for axis in range(self.joystick.get_numaxes()):
            pygame.event.pump()
            current_val = self.joystick.get_axis(axis)
            baseline = self.assignment_start_state.get(("axis", axis), True)
            if (not baseline) and (current_val > 0):
                self.mapping[action["name"]] = {"input_type": "axis", "index": axis}
                self.action_rows[action["name"]]["label"].config(text=f"Axis {axis}")
                self.log(f"Assigned '{action['name']}' to Axis {axis} (value: {current_val:.3f}).")
                self._current_assignment_action = None
                return
        self.after(self.poll_interval, self.check_assignment_input)

    # -----------------------------
    # Monitoring Methods (Auto-Monitoring)
    # -----------------------------
    def monitor_loop(self):
        # If an assignment is in progress, skip monitoring.
        if self._current_assignment_action is not None:
            self.after(self.poll_interval, self.monitor_loop)
            return

        pygame.event.pump()
        for action in self.actions:
            act_name = action["name"]
            mapping = self.mapping.get(act_name)
            if mapping is None:
                continue
            new_state = False
            # For a button mapping, get the boolean state.
            if mapping["input_type"] == "button":
                try:
                    current_val = bool(self.joystick.get_button(mapping["index"]))
                    new_state = current_val
                except Exception as e:
                    self.log(f"Error reading button {mapping['index']}: {e}")
            # For an axis mapping, use a rising edge with hysteresis.
            elif mapping["input_type"] == "axis":
                try:
                    val = self.joystick.get_axis(mapping["index"])
                except Exception as e:
                    self.log(f"Error reading axis {mapping['index']}: {e}")
                    continue
                # Hysteresis: active if value > toggle_threshold; inactive if below (toggle_threshold - 0.5)
                if val > self.toggle_threshold:
                    new_state = True
                elif val < (self.toggle_threshold - 0.5):
                    new_state = False
                else:
                    new_state = self.action_last_state.get(act_name, False)
            last_state = self.action_last_state.get(act_name, False)
            # For button mappings, trigger on falling edge (release).
            if mapping["input_type"] == "button":
                if last_state and not new_state:
                    send_key(action["vk"])
                    self.log(f"Action '{act_name}' triggered (button release).")
                    self.action_last_state[act_name] = False
                elif not last_state and new_state:
                    self.action_last_state[act_name] = True
            else:
                # For axis mappings, trigger on rising edge.
                if (not last_state) and new_state:
                    send_key(action["vk"])
                    self.log(f"Action '{act_name}' triggered (axis rising edge).")
                    self.action_last_state[act_name] = True
                elif last_state and not new_state:
                    self.action_last_state[act_name] = False
        self.after(self.poll_interval, self.monitor_loop)

# -----------------------------
# Main entry point
# -----------------------------
if __name__ == "__main__":
    app = SimMusicSwitcher()
    app.mainloop()
