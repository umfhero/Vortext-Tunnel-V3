import customtkinter as ctk
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox
import socket
import threading
import os
import json
import uuid
from PIL import Image, ImageTk
from tkinterdnd2 import DND_FILES, TkinterDnD
import base64
import time
import shutil  # add at top

# --- Application Version ---
VERSION = "4.0.1"  # Defined VERSION here

# --- Custom Tooltip Class ---


class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.widget.bind("<Enter>", self.show_tooltip)
        self.widget.bind("<Leave>", self.hide_tooltip)

    def show_tooltip(self, event):
        if self.tooltip_window or not self.text:
            return
        x, y, _, _ = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25
        self.tooltip_window = tk.Toplevel(self.widget)
        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.wm_geometry(f"+{x}+{y}")
        label = tk.Label(self.tooltip_window, text=self.text, justify='left',
                         background="#2b2b2b", relief='solid', borderwidth=1,
                         font=("Arial", "12", "normal"), fg="white")
        label.pack(ipadx=1)

    def hide_tooltip(self, event):
        if self.tooltip_window:
            self.tooltip_window.destroy()
        self.tooltip_window = None

# --- Custom Dialogs ---


class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, master, app_instance):
        super().__init__(master)
        self.app = app_instance
        self.title("Settings")
        self.geometry("400x300")
        self.transient(master)
        self.grab_set()
        self.attributes('-alpha', 1.0)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        ctk.CTkLabel(self, text="Vortex Tunnel Settings",
                     font=ctk.CTkFont(size=24, weight="bold")).pack(pady=20)
        info_frame = ctk.CTkFrame(self)
        info_frame.pack(pady=10, padx=20, fill="x")
        ctk.CTkLabel(info_frame, text=f"Version: {VERSION}", font=ctk.CTkFont(
            size=14)).pack(anchor="w", padx=10)
        ctk.CTkLabel(info_frame, text=f"My Name: {self.app.my_name or 'Not Selected'}", font=ctk.CTkFont(
            size=14)).pack(anchor="w", padx=10)
        ctk.CTkLabel(info_frame, text=f"Peer Name: {self.app.peer_name or 'Not Connected'}", font=ctk.CTkFont(
            size=14)).pack(anchor="w", padx=10)

        ctk.CTkButton(self, text="Check for Updates",
                      font=ctk.CTkFont(size=14)).pack(pady=10)
        ctk.CTkButton(self, text="Close", command=self.destroy_dialog,
                      font=ctk.CTkFont(size=14)).pack(pady=10)

    def _on_close(self):
        if hasattr(self.master, 'attributes'):
            self.master.attributes('-alpha', 1.0)
        self.destroy()

    def destroy_dialog(self):
        self._on_close()

    def check_for_updates(self):
        messagebox.showinfo(
            "Update Check", "You are on the latest version of Vortex Tunnel.")

# --- Main Application ---


class VortexTunnelApp(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.master = master
        app_data_dir = os.path.join(os.getenv('APPDATA'), 'Vortex Tunnel')
        os.makedirs(app_data_dir, exist_ok=True)
        self.NATHAN_NAME, self.MAJID_NAME = "Majid 2.0", "Majid"
        self.NATHAN_IP, self.MAJID_IP = "100.92.141.68", "100.93.161.73"
        self.my_name, self.peer_name = None, None
        self.config_file = os.path.join(app_data_dir, "config.json")
        self.chat_history_file = os.path.join(app_data_dir, "chat_history.log")
        self.downloads_folder = os.path.join(app_data_dir, "Vortex_Downloads")
        os.makedirs(self.downloads_folder, exist_ok=True)
        self.file_gallery_metadata_file = os.path.join(
            app_data_dir, "file_gallery.json")

        self.host_ip_listen, self.port = "0.0.0.0", 12345
        self.connection, self.connected = None, threading.Event()
        self.pending_transfers, self.chat_messages = {}, {}
        self.file_gallery_items_metadata = {}
        self.file_gallery_widgets = {}
        # Profiles mapping
        self.profiles = {"Majid": "100.93.161.73",
                         "Nathan": "100.122.120.65", "Majid 2.0": "100.92.141.68"}
        # Filtering and search state
        self.filter_state = "All"
        self.search_query = ""

        self._create_widgets()
        self.load_config_and_history()
        self.start_server()

    def _create_widgets(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.main_container_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container_frame.grid(
            row=0, column=0, rowspan=3, padx=30, pady=0, sticky="nsew")
        self.main_container_frame.grid_columnconfigure(0, weight=1)
        self.main_container_frame.grid_rowconfigure(1, weight=1)

        top_frame = ctk.CTkFrame(self.main_container_frame)
        top_frame.grid(row=0, column=0, padx=0, pady=10, sticky="ew")

        # ...existing code (settings and pin remain in top_frame)...
        self.settings_button = ctk.CTkButton(
            top_frame, text="⚙️", width=30, font=ctk.CTkFont(size=18), command=self.open_settings)
        self.settings_button.pack(side="left", padx=5, pady=5)
        self.pin_button = ctk.CTkButton(top_frame, text="📌", width=30, font=ctk.CTkFont(
            size=18), command=self.toggle_topmost)
        self.pin_button.pack(side="left", padx=5, pady=5)
        self.is_pinned = False

        # Removed 'segmented_button_font' as it's not a supported argument
        self.tab_view = ctk.CTkTabview(self.main_container_frame)
        self.tab_view.grid(row=1, column=0, padx=0,
                           pady=(0, 10), sticky="nsew")

        # Reordered tabs
        self.tab_view.add("Files")
        self.tab_view.add("Drawing")
        self.tab_view.add("Chat")

        # Removed the problematic _text_label configuration (it was already removed in the previous fix,
        # but just double-checking to ensure no re-introduction)

        self._create_files_tab()  # Create files tab first
        self._create_drawing_tab()
        self._create_chat_tab()

        self.tab_view.set("Files")  # Set Files tab as default

        bottom_frame = ctk.CTkFrame(self.main_container_frame)
        bottom_frame.grid(row=2, column=0, padx=0, pady=(0, 10), sticky="ew")
        # Profile label and dropdown
        ctk.CTkLabel(bottom_frame, text="Profile:", font=ctk.CTkFont(
            size=14)).pack(side="left", padx=5, pady=5)
        self.identity_menu = ctk.CTkOptionMenu(bottom_frame, values=list(
            self.profiles.keys()), font=ctk.CTkFont(size=14), command=self._identity_selected)
        self.identity_menu.pack(side="left", padx=5, pady=5)
        # Default to first profile if none selected
        if not self.identity_menu.get():
            first_profile = list(self.profiles.keys())[0]
            self.identity_menu.set(first_profile)
            self._identity_selected(first_profile)
        # Connect-to label and dropdown
        ctk.CTkLabel(bottom_frame, text="Connect to:", font=ctk.CTkFont(
            size=14)).pack(side="left", padx=5, pady=5)
        self.peer_menu = ctk.CTkOptionMenu(bottom_frame, values=list(
            self.profiles.keys()), font=ctk.CTkFont(size=14), command=self._peer_selected)
        self.peer_menu.pack(side="left", padx=5, pady=5)
        # Connect button
        self.connect_button = ctk.CTkButton(bottom_frame, text="Connect", font=ctk.CTkFont(
            size=14), command=self.connect_to_peer)
        self.connect_button.pack(side="left", padx=5, pady=5)
        # ...existing code...

    def _create_chat_tab(self):
        chat_tab = self.tab_view.tab("Chat")
        chat_tab.grid_columnconfigure(0, weight=1)
        chat_tab.grid_rowconfigure(0, weight=1)
        self.chat_frame = ctk.CTkScrollableFrame(chat_tab)
        self.chat_frame.grid(row=0, column=0, sticky="nsew")
        input_frame = ctk.CTkFrame(chat_tab, fg_color="transparent")
        input_frame.grid(row=1, column=0, sticky="ew")
        input_frame.grid_columnconfigure(0, weight=1)

        self.chat_entry = ctk.CTkEntry(
            input_frame, placeholder_text="Type a message or drag a file here...", font=ctk.CTkFont(size=14))
        self.chat_entry.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        self.chat_entry.bind("<Return>", lambda e: self.send_chat_message())
        self.send_button = ctk.CTkButton(input_frame, text="Send", font=ctk.CTkFont(
            size=14), command=self.send_chat_message)
        self.send_button.grid(row=0, column=1, padx=5, pady=5)

    def _create_drawing_tab(self):
        draw_tab = self.tab_view.tab("Drawing")
        draw_tab.grid_columnconfigure(0, weight=1)
        draw_tab.grid_rowconfigure(1, weight=1)
        controls = ctk.CTkFrame(draw_tab)
        controls.grid(row=0, column=0, sticky="ew")
        self.color, self.brush_size = "#FFFFFF", 3

        ctk.CTkButton(controls, text="Color", font=ctk.CTkFont(
            size=14), command=self.choose_color).pack(side="left", padx=5, pady=5)
        ctk.CTkSlider(controls, from_=1, to=50, command=lambda v: setattr(
            self, 'brush_size', int(v))).pack(side="left", expand=True, fill="x")
        ctk.CTkButton(controls, text="Clear Canvas", font=ctk.CTkFont(
            size=14), command=self.clear_canvas).pack(side="right", padx=5, pady=5)

        self.canvas = tk.Canvas(draw_tab, bg="#1a1a1a", highlightthickness=0)
        self.canvas.grid(row=1, column=0, sticky="nsew")
        self.old_x, self.old_y = None, None
        self.remote_mouse = None
        self.remote_mouse_id = None
        self.remote_mouse_label_id = None
        self.canvas.bind("<B1-Motion>", self.draw)
        self.canvas.bind("<ButtonRelease-1>", self.reset_drawing_state)
        self.canvas.bind("<Motion>", self.send_mouse_position)
        self.canvas.bind("<Leave>", self.send_mouse_leave)
        self.canvas.after(100, self.check_remote_mouse_timeout)

    def _create_files_tab(self):
        files_tab = self.tab_view.tab("Files")
        files_tab.grid_columnconfigure(0, weight=1)
        files_tab.grid_rowconfigure(0, weight=0)
        files_tab.grid_rowconfigure(1, weight=1)

        # Filter and Search Controls
        control_frame = ctk.CTkFrame(files_tab, fg_color="transparent")
        control_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        control_frame.grid_columnconfigure(1, weight=1)
        self.filter_button = ctk.CTkButton(control_frame, text="Filter: All", width=100,
                                           command=self._cycle_filter)
        self.filter_button.grid(row=0, column=0, padx=5)
        self.search_entry = ctk.CTkEntry(
            control_frame, placeholder_text="Search files...", font=ctk.CTkFont(size=14))
        self.search_entry.grid(row=0, column=1, padx=5, sticky="ew")
        self.search_entry.bind("<KeyRelease>", lambda e: self._on_search())

        self.gallery_frame = ctk.CTkScrollableFrame(
            files_tab, label_text="Shared File Gallery")
        self.gallery_frame.grid(row=1, column=0, sticky="nsew")
        # Use the CTkScrollableFrame itself as container for file items
        self.gallery_container = self.gallery_frame
        # Initialize layout counters
        self.gallery_item_row_counter = 0
        self.gallery_item_col_counter = 0
        # Configure columns in gallery container for uniform grid layout
        for i in range(4):
            self.gallery_container.grid_columnconfigure(
                i, weight=1, uniform="file_item")
        # Populate initial view
        self._apply_filter_search()
    # Placeholder method for drag-drop label visibility (stub for compatibility)

    def _update_drag_drop_label_visibility(self):
        pass

    def _cycle_filter(self):
        # Cycle through filter states
        options = ["All", "Sent", "Received"]
        idx = options.index(self.filter_state)
        self.filter_state = options[(idx + 1) % len(options)]
        self.filter_button.configure(text=f"Filter: {self.filter_state}")
        self._apply_filter_search()

    def _on_search(self):
        self.search_query = self.search_entry.get().lower()
        self._apply_filter_search()

    def _apply_filter_search(self):
        """Re-layout gallery items based on filter and search state."""
        # Clear existing
        for widget in self.file_gallery_widgets.values():
            widget.grid_forget()
        row, col = 0, 0
        for file_id, data in self.file_gallery_items_metadata.items():
            name = data['filename']
            local = data['local_path']
            # Filter by state
            if self.filter_state == 'Sent' and local.startswith(self.downloads_folder):
                continue
            if self.filter_state == 'Received' and not local.startswith(self.downloads_folder):
                continue
            # Filter by search
            if self.search_query and self.search_query not in name.lower():
                continue
            widget = self.file_gallery_widgets.get(file_id)
            if widget:
                widget.grid(in_=self.gallery_container, row=row, column=col,
                            padx=5, pady=5, sticky="nsew")
                col += 1
                if col >= 4:
                    col = 0
                    row += 1
        # Refresh layout
        # Refresh layout
        self.gallery_container.update_idletasks()

    def open_settings(self):
        SettingsDialog(self.master, self)

    def choose_color(self): color_code = colorchooser.askcolor(
        title="Choose color"); self.color = color_code[1] if color_code else self.color

    def toggle_topmost(self): self.is_pinned = not self.is_pinned; self.master.attributes("-topmost", self.is_pinned); self.pin_button.configure(
        fg_color=("#3b8ed0", "#1f6aa5") if self.is_pinned else ctk.ThemeManager.theme["CTkButton"]["fg_color"])

    def handle_drop(self, event):
        # Handle multiple dropped files, strip braces for paths with spaces
        paths = self.master.tk.splitlist(event.data)
        for path in paths:
            clean_path = path
            if clean_path.startswith("{") and clean_path.endswith("}"):
                clean_path = clean_path[1:-1]
            self.send_file(clean_path)

    def add_chat_message(self, msg_id, sender, message, is_own, is_file=False, file_info=None):
        if msg_id in self.chat_messages:
            return
        row_frame = ctk.CTkFrame(self.chat_frame, fg_color="transparent")
        row_frame.pack(fill="x", padx=5, pady=2)
        row_frame.grid_columnconfigure(1 if is_own else 0, weight=1)
        msg_frame = ctk.CTkFrame(row_frame)
        msg_frame.grid(row=0, column=1 if is_own else 0,
                       sticky="e" if is_own else "w")

        ctk.CTkLabel(msg_frame, text=f"{sender}:", font=ctk.CTkFont(
            weight="bold", size=14)).pack(side="left", padx=(10, 5), pady=5)
        if is_file:
            file_frame = ctk.CTkFrame(msg_frame, fg_color="gray20")
            file_frame.pack(side="left", padx=5, pady=5)
            ctk.CTkLabel(file_frame, text=f"📄 {file_info['name']}", wraplength=150, font=ctk.CTkFont(
                size=14)).pack(anchor="w")
            ctk.CTkLabel(file_frame, text=f"Size: {file_info['size']:.2f} MB", font=(
                "Arial", 11)).pack(anchor="w")
            ctk.CTkButton(file_frame, text="Download", font=ctk.CTkFont(
                size=14), command=lambda id=file_info['id'], name=file_info['name']: self.request_file_download(id, name)).pack(pady=5)
        else:
            msg_label = ctk.CTkLabel(msg_frame, text=message, wraplength=self.winfo_width(
            ) - 250, justify="left", font=ctk.CTkFont(size=14))
            msg_label.pack(side="left", padx=5, pady=5, expand=True, fill="x")
        if is_own and not is_file:
            btn_frame = ctk.CTkFrame(msg_frame, fg_color="transparent")
            btn_frame.pack(side="right", padx=5, pady=5)
            ctk.CTkButton(btn_frame, text="✏️", width=20, font=ctk.CTkFont(
                size=18), command=lambda id=msg_id: self.edit_chat_prompt(id)).pack()
            ctk.CTkButton(btn_frame, text="🗑️", width=20, font=ctk.CTkFont(
                size=18), command=lambda id=msg_id: self.send_command(f"DELETE_MSG:{id}")).pack(pady=(2, 0))
        self.chat_messages[msg_id] = row_frame
        self.after(100, self.chat_frame._parent_canvas.yview_moveto, 1.0)

    def send_chat_message(self, msg_id_to_edit=None):
        msg = self.chat_entry.get()
        if not msg or not self.my_name:
            return
        cmd = "EDIT_MSG" if msg_id_to_edit else "CHAT_MSG"
        msg_id = msg_id_to_edit if msg_id_to_edit else str(uuid.uuid4())
        full_command = f"{cmd}:{msg_id}:{self.my_name}:{msg}"
        self.send_command(full_command)
        self.process_command(full_command)
        self.chat_entry.delete(0, tk.END)
        if msg_id_to_edit:
            self.send_button.configure(
                text="Send", command=self.send_chat_message)

    def edit_chat_prompt(self, msg_id):
        frame = self.chat_messages[msg_id].winfo_children()[0]
        if len(frame.winfo_children()) > 1 and isinstance(frame.winfo_children()[1], ctk.CTkLabel):
            original_text = frame.winfo_children()[1].cget("text")
            self.chat_entry.delete(0, tk.END)
            self.chat_entry.insert(0, original_text)
            self.send_button.configure(
                text="Save", command=lambda: self.send_chat_message(msg_id_to_edit=msg_id))
        else:
            messagebox.showinfo(
                "Cannot Edit", "This message type cannot be edited.")

    def confirm_clear_chat(self):
        if messagebox.askyesno("Confirm", "Are you sure you want to clear the chat history for everyone?"):
            self.send_command("CLEAR_CHAT")

    def add_file_to_gallery(self, file_id, filename, local_path):
        """Adds a new file entry to metadata, creates widget, and refreshes layout."""
        if not os.path.exists(local_path):
            print(
                f"File not found at {local_path}, skipping gallery addition.")
            return
        # Store metadata and persist
        self.file_gallery_items_metadata[file_id] = {
            "filename": filename, "local_path": local_path}
        self._save_file_gallery_metadata()
        # Avoid duplicate widgets
        if file_id in self.file_gallery_widgets:
            return
        # Create frame in gallery container
        file_frame = ctk.CTkFrame(self.gallery_container, width=150, height=150,
                                  corner_radius=10, fg_color="gray15",
                                  border_width=1, border_color="gray30")
        file_frame.grid_propagate(False)
        # Thumbnail or icon
        try:
            img = Image.open(local_path)
            img.thumbnail((96, 96))
            thumb = ImageTk.PhotoImage(img)
            ctk.CTkLabel(file_frame, image=thumb, text="").pack(pady=(10, 5))
            file_frame.image = thumb
        except Exception:
            ctk.CTkLabel(file_frame, text="📄", font=("Arial", 48), width=96,
                         height=96, fg_color="gray25", corner_radius=6).pack(pady=(10, 5))
        # Filename and extension
        ctk.CTkLabel(file_frame, text=filename, wraplength=120,
                     font=ctk.CTkFont(size=13, weight="bold")).pack()
        ext = os.path.splitext(filename)[1].upper()[1:] or "FILE"
        ctk.CTkLabel(file_frame, text=ext, font=("Arial", 11, "italic"),
                     text_color="gray").pack(pady=(0, 5))
        # Buttons
        btn_frame = ctk.CTkFrame(file_frame, fg_color="transparent")
        btn_frame.pack(pady=(0, 10))
        if local_path.startswith(self.downloads_folder):
            ctk.CTkButton(btn_frame, text="Download", width=70,
                          command=lambda fid=file_id: self.download_file(fid)
                          ).pack(side="left", padx=2)
        else:
            ctk.CTkButton(btn_frame, text="Open", width=70,
                          command=lambda p=local_path: os.startfile(p)
                          ).pack(side="left", padx=2)
        ctk.CTkButton(btn_frame, text="Delete", width=70,
                      fg_color="#D32F2F", hover_color="#B71C1C",
                      command=lambda fid=file_id, p=local_path: self.confirm_delete_file(
                          fid, p)
                      ).pack(side="right", padx=2)
        # Register widget and refresh layout
        self.file_gallery_widgets[file_id] = file_frame
        self._apply_filter_search()

    def _save_file_gallery_metadata(self):
        files_to_save = []
        for file_id, data in self.file_gallery_items_metadata.items():
            files_to_save.append({
                "file_id": file_id,
                "filename": data["filename"],
                "local_path": data["local_path"]
            })
        try:
            with open(self.file_gallery_metadata_file, 'w') as f:
                json.dump(files_to_save, f, indent=4)
        except Exception as e:
            print(f"Error saving file gallery metadata: {e}")

    def load_config_and_history(self):
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                # Restore last used profile
                last_profile = config.get("last_profile")
                if last_profile and last_profile in self.profiles:
                    self.identity_menu.set(last_profile)
                    self._identity_selected(last_profile)
                # Restore last connected peer
                last_peer = config.get("last_peer")
                if last_peer and last_peer in self.profiles:
                    self.peer_menu.set(last_peer)
                    self._peer_selected(last_peer)

            if os.path.exists(self.chat_history_file):
                with open(self.chat_history_file, 'r') as f:
                    for line in f:
                        self.process_command(line.strip(), from_history=True)

            # Load file gallery metadata
            if os.path.exists(self.file_gallery_metadata_file):
                with open(self.file_gallery_metadata_file, 'r') as f:
                    loaded_files = json.load(f)
                self.gallery_item_row_counter = 0
                self.gallery_item_col_counter = 0
                valid_files = []
                for file_data in loaded_files:
                    file_id = file_data.get("file_id")
                    filename = file_data.get("filename")
                    local_path = file_data.get("local_path")
                    if file_id and filename and local_path and os.path.exists(local_path):
                        valid_files.append(file_data)
                        self.add_file_to_gallery(file_id, filename, local_path)
                    else:
                        print(
                            f"Skipping invalid/missing file from history: {file_data}")
                self.file_gallery_items_metadata = {
                    f['file_id']: f for f in valid_files}
                self._save_file_gallery_metadata()
                # Update visibility and layout after loading history
                self._update_drag_drop_label_visibility()
                self._apply_filter_search()

        except Exception as e:
            print(f"Error loading config or history: {e}")

    def on_closing(self):
        # Save last used profile and peer selections
        config = {
            "last_profile": self.identity_menu.get() if self.my_name else None,
            "last_peer": self.peer_menu.get() if self.peer_name else None
        }
        try:
            with open(self.config_file, 'w') as f:
                json.dump(config, f)
        except Exception as e:
            print(f"Error saving config: {e}")

        self._save_file_gallery_metadata()

        if self.connection:
            self.connection.close()
        self.master.destroy()

    def process_command(self, command_str, from_history=False):
        try:
            cmd = command_str.split(":", 1)[0]
            if cmd == "CHAT_MSG":
                _, msg_id, sender, message = command_str.split(":", 3)
                self.add_chat_message(
                    msg_id, sender, message, is_own=(sender == self.my_name))
            elif cmd == "EDIT_MSG":
                _, msg_id, _, new_message = command_str.split(":", 3)
                if msg_id in self.chat_messages:
                    msg_frame = self.chat_messages[msg_id].winfo_children()[0]
                    if len(msg_frame.winfo_children()) > 1 and isinstance(msg_frame.winfo_children()[1], ctk.CTkLabel):
                        msg_frame.winfo_children()[1].configure(
                            text=new_message)
            elif cmd == "DELETE_MSG":
                _, msg_id = command_str.split(":", 1)
                if msg_id in self.chat_messages:
                    self.chat_messages[msg_id].destroy()
                    del self.chat_messages[msg_id]
            elif cmd == "CLEAR_CHAT":
                [w.destroy() for w in self.chat_messages.values()]
                self.chat_messages.clear()
            elif cmd == "DRAW":
                _, coords = command_str.split(":", 1)
                x1, y1, x2, y2, color, size = coords.split(",")
                self.canvas.create_line(int(x1), int(y1), int(x2), int(y2), width=float(
                    size), fill=color, capstyle=tk.ROUND, smooth=tk.TRUE)
            elif cmd == "CLEAR":
                self.canvas.delete("all")
            elif cmd == "MOUSE_MOVE":
                _, data = command_str.split(":", 1)
                x, y, name = data.split(",", 2)
                self.update_remote_mouse(int(x), int(y), name)
            elif cmd == "MOUSE_LEAVE":
                self.clear_remote_mouse()
            elif cmd == "FILE_REQUEST":
                _, file_id, filename, filesize = command_str.split(":", 3)
                self.pending_transfers[file_id] = {
                    "filename": filename, "filesize": int(filesize)}
                self.send_command(f"FILE_ACCEPT:{file_id}")
                self.update_status(
                    f"Automatically accepting incoming file: '{filename}'", "blue")
            elif cmd == "FILE_ACCEPT":
                _, file_id = command_str.split(":", 1)
                if file_id in self.pending_transfers:
                    threading.Thread(target=self._send_file_data, args=(
                        file_id,), daemon=True).start()
                else:
                    print(
                        f"Received FILE_ACCEPT for unknown file_id: {file_id}")
            elif cmd == "FILE_REJECT":
                _, file_id = command_str.split(":", 1)
                if file_id in self.pending_transfers:
                    del self.pending_transfers[file_id]
                self.update_status("File transfer rejected by peer.", "orange")
            elif cmd == "ADD_TO_GALLERY":
                _, file_id, filename = command_str.split(":", 2)
                local_path = os.path.join(
                    self.downloads_folder, f"{file_id}_{filename}")
                self.add_file_to_gallery(file_id, filename, local_path)
            elif cmd == "REQUEST_DOWNLOAD":
                _, file_id = command_str.split(":", 1)
                if file_id in self.file_gallery_items_metadata:
                    filepath_to_send = self.file_gallery_items_metadata[file_id]['local_path']
                    self.pending_transfers[file_id] = {
                        "filepath": filepath_to_send,
                        "filename": os.path.basename(filepath_to_send),
                        "filesize": os.path.getsize(filepath_to_send)
                    }
                    threading.Thread(target=self._send_file_data, args=(
                        file_id,), daemon=True).start()
                else:
                    print(
                        f"Error: Peer requested download for unknown file_id: {file_id}")
            elif cmd == "DELETE_FILE_COMMAND":
                _, file_id = command_str.split(":", 1)
                local_path_to_delete = None
                if file_id in self.file_gallery_items_metadata:
                    local_path_to_delete = self.file_gallery_items_metadata[file_id]['local_path']
                self.delete_file(file_id, local_path_to_delete,
                                 is_remote_command=True)

            if not from_history:
                self.notify_user()
            if not from_history and cmd in ["CHAT_MSG", "EDIT_MSG", "DELETE_MSG", "CLEAR_CHAT", "ADD_TO_GALLERY", "DELETE_FILE_COMMAND"]:
                with open(self.chat_history_file, 'a' if cmd != "CLEAR_CHAT" else 'w') as f:
                    if cmd != "CLEAR_CHAT":
                        f.write(command_str + '\n')
        except Exception as e:
            print(f"Error processing command: {e} -> '{command_str}'")

    def receive_data(self):
        buffer = b""
        separator = b"\n"
        receiving_file_info = None
        while self.connected.is_set():
            try:
                chunk = self.connection.recv(8192)
                if not chunk:
                    self.handle_disconnect()
                    break

                if receiving_file_info:
                    buffer += chunk
                    filepath, filesize, file_id, original_filename = receiving_file_info['path'], receiving_file_info[
                        'size'], receiving_file_info['id'], receiving_file_info['original_filename']

                    if len(buffer) >= filesize:
                        file_data, buffer = buffer[:filesize], buffer[filesize:]
                        with open(filepath, 'wb') as f:
                            f.write(file_data)
                        self.update_status(
                            f"Successfully received {original_filename}", "green")
                        self.after(10, self.add_file_to_gallery,
                                   file_id, original_filename, filepath)
                        receiving_file_info = None
                    continue

                buffer += chunk
                while separator in buffer:
                    line_bytes, buffer = buffer.split(separator, 1)
                    command_str = line_bytes.decode('utf-8', errors='ignore')

                    if command_str.startswith("FILE_START_TRANSFER"):
                        _, file_id, filename_from_cmd, filesize_str = command_str.split(
                            ":", 3)

                        save_filename = filename_from_cmd
                        if file_id in self.pending_transfers and 'filename' in self.pending_transfers[file_id]:
                            save_filename = self.pending_transfers[file_id]['filename']

                        save_path = os.path.join(
                            self.downloads_folder, f"{file_id}_{save_filename}")

                        if save_path:
                            receiving_file_info = {"id": file_id, "path": save_path, "size": int(
                                filesize_str), "original_filename": save_filename}

                            if len(buffer) >= int(filesize_str):
                                file_data, buffer = buffer[:int(
                                    filesize_str)], buffer[int(filesize_str):]
                                with open(save_path, 'wb') as f:
                                    f.write(file_data)
                                self.update_status(
                                    f"Successfully received {save_filename}", "green")
                                self.after(10, self.add_file_to_gallery,
                                           file_id, save_filename, save_path)
                                receiving_file_info = None
                        continue
                    elif command_str:
                        self.process_command(command_str)
            except Exception as e:
                print(f"Receive loop error: {e}")
                self.update_status(f"Connection error: {e}", "red")
                self.handle_disconnect()
                break

    def send_command(self, data_str):
        # Send data if socket exists
        if self.connection:
            try:
                self.connection.sendall((data_str + "\n").encode('utf-8'))
            except Exception as e:
                print(f"Error sending command: {e}")
                self.handle_disconnect()
        else:
            print("Not connected, cannot send command.")

    def send_file(self, local_path):
        """Initiate a file transfer by sending a request to the peer."""
        if not os.path.exists(local_path):
            self.update_status(f"File not found: {local_path}", "red")
            return
        file_id = str(uuid.uuid4())
        filename = os.path.basename(local_path)
        filesize = os.path.getsize(local_path)
        self.pending_transfers[file_id] = {
            "filename": filename, "filepath": local_path, "filesize": filesize}
        # Request peer to accept the file transfer
        self.send_command(f"FILE_REQUEST:{file_id}:{filename}:{filesize}")
        self.update_status(f"Initiated file transfer: {filename}", "white")
        # Add locally to gallery for sender view
        self.add_file_to_gallery(file_id, filename, local_path)

    def _send_file_data(self, file_id):
        """Send the actual file data after peer accepts the transfer."""
        transfer = self.pending_transfers.get(file_id)
        if not transfer:
            print(f"No pending transfer for file_id: {file_id}")
            return
        filepath = transfer.get("filepath")
        filesize = transfer.get("filesize")
        filename = transfer.get("filename")
        # Notify peer to start transfer
        self.send_command(
            f"FILE_START_TRANSFER:{file_id}:{filename}:{filesize}")
        try:
            with open(filepath, 'rb') as f:
                while True:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    self.connection.sendall(chunk)
            self.update_status(f"File sent: {filename}", "green")
        except Exception as e:
            print(f"Error sending file data: {e}")
            self.update_status(f"Failed to send file: {filename}", "red")
        # Clean up pending transfer
        if file_id in self.pending_transfers:
            del self.pending_transfers[file_id]

    def _identity_selected(self, identity):
        self.my_name = identity
        self.update_status(f"Identity set to: {identity}", "white")

    def _peer_selected(self, peer):
        self.peer_name = peer
        # status updated on connect
        pass

    def connect_to_peer(self):
        """Establish a client connection to the selected peer."""
        peer = self.peer_menu.get()
        peer_ip = self.profiles.get(peer)
        if not peer_ip:
            return
        try:
            # Close existing connection if any
            if self.connection:
                self.connection.close()
            # Create and connect socket
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.connect((peer_ip, self.port))
            self.connection = client
            self.connected.set()
            self.peer_name = peer
            # Start receiving loop
            threading.Thread(target=self.receive_data, daemon=True).start()
            # Log success to console
            print(f"Connected to {peer} at {peer_ip}")
        except Exception as e:
            # Connection failed
            print(f"Connection failed to {peer_ip}: {e}")

    def start_server(self):
        """Start the TCP server to listen for incoming connections."""
        def accept_loop():
            while True:
                try:
                    client_socket, addr = self.server.accept()
                    print(f"Accepted connection from {addr}")
                    self.connection = client_socket
                    self.connected.set()
                    self.update_status(f"Connected to {addr}", "green")
                    # Start receiving data from the client
                    self.receive_data()
                except Exception as e:
                    print(f"Error in accept loop: {e}")
                    break

        def run_server():
            self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server.bind((self.host_ip_listen, self.port))
            self.server.listen(5)
            print(
                f"Listening for connections on {self.host_ip_listen}:{self.port}")
            self.update_status(
                f"Listening for connections on {self.host_ip_listen}:{self.port}", "white")
            accept_loop()

        threading.Thread(target=run_server, daemon=True).start()

    def handle_disconnect(self):
        """Handle cleanup and UI updates on disconnect."""
        self.connected.clear()
        if self.connection:
            self.connection.close()
            self.connection = None
        self.update_status("Disconnected", "red")
        # Clear remote mouse and other states
        self.clear_remote_mouse()
        self.canvas.delete("all")
        # Reset file transfers
        self.pending_transfers.clear()
        # Refresh gallery
        self._apply_filter_search()

    def update_status(self, message, color="white"):
        """Suppress status updates in UI."""
        pass

    def notify_user(self):
        """Show a notification to the user (stub implementation)."""
        print("Notification: You have a new message or update.")

    def clear_canvas(self):
        """Clear the drawing canvas."""
        self.canvas.delete("all")

    def draw(self, event):
        """Handle drawing on the canvas."""
        if self.old_x and self.old_y:
            x, y = event.x, event.y
            self.canvas.create_line(self.old_x, self.old_y, x, y, width=self.brush_size,
                                    fill=self.color, capstyle=tk.ROUND, smooth=tk.TRUE)
            self.old_x, self.old_y = x, y
            # Send draw command to peer
            self.send_command(
                f"DRAW:{self.old_x},{self.old_y},{x},{y},{self.color},{self.brush_size}")
        else:
            self.old_x, self.old_y = event.x, event.y

    def reset_drawing_state(self, event):
        """Reset the drawing state on mouse release."""
        self.old_x, self.old_y = None, None

    def send_mouse_position(self, event):
        """Send the mouse position to the peer."""
        x, y = event.x, event.y
        self.send_command(f"MOUSE_MOVE:{x},{y},{self.my_name}")

    def send_mouse_leave(self, event):
        """Handle mouse leave event."""
        self.send_command(f"MOUSE_LEAVE:{self.my_name}")

    def update_remote_mouse(self, x, y, name):
        """Update the position of the remote mouse cursor."""
        if not self.remote_mouse or not self.remote_mouse_id:
            # Create remote mouse indicator
            self.remote_mouse = self.canvas.create_oval(
                x-5, y-5, x+5, y+5, fill="red")
            self.remote_mouse_id = self.remote_mouse
            # Create label for remote mouse name
            self.remote_mouse_label_id = self.canvas.create_text(
                x, y-10, text=name, fill="white", font=("Arial", 10))
        else:
            # Move existing remote mouse indicator
            self.canvas.coords(self.remote_mouse_id, x-5, y-5, x+5, y+5)
            # Move label
            self.canvas.coords(self.remote_mouse_label_id, x, y-10)

    def clear_remote_mouse(self):
        """Clear the remote mouse indicator."""
        if self.remote_mouse_id:
            self.canvas.delete(self.remote_mouse_id)
            self.remote_mouse_id = None
        if self.remote_mouse_label_id:
            self.canvas.delete(self.remote_mouse_label_id)
            self.remote_mouse_label_id = None

    def check_remote_mouse_timeout(self):
        """Periodic check stub to clear remote mouse on timeout or for scheduling."""
        # TODO: implement timeout logic when needed
        # Reschedule next check
        self.canvas.after(100, self.check_remote_mouse_timeout)

    def download_file(self, file_id):
        """Prompt user to save the selected file from the gallery."""
        # Get source path and original filename
        data = self.file_gallery_items_metadata.get(file_id)
        if not data:
            return
        src_path = data['local_path']
        default_name = data['filename']
        # Ask where to save
        save_path = filedialog.asksaveasfilename(initialfile=default_name)
        if save_path:
            try:
                shutil.copy(src_path, save_path)
            except Exception as e:
                print(f"Error saving file: {e}")


if __name__ == '__main__':
    # Initialize the TkinterDnD root window
    root = TkinterDnD.Tk()
    root.title("Vortex Tunnel")
    # Set appearance mode and color theme
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")
    # Create and pack the main application frame
    app = VortexTunnelApp(root)
    app.pack(expand=True, fill='both')
    # Enable drag-and-drop
    root.drop_target_register(DND_FILES)
    root.dnd_bind('<<Drop>>', app.handle_drop)
    # Handle window close
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    # Start the GUI loop
    root.mainloop()
