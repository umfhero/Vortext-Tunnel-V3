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
import sys  # Import sys for resource_path helper
import struct  # For packing/unpacking data length

# --- Application Version ---
VERSION = "V0.2.0"

# --- Helper for PyInstaller resource path ---


def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temporary folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except AttributeError:
        # Not running in PyInstaller bundle, use current directory
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

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
        # Corrected Nathan/Majid 2.0 names
        self.NATHAN_NAME, self.MAJID_NAME, self.NATHAN2_NAME = "Nathan", "Majid", "Majid 2.0"
        self.NATHAN_IP, self.MAJID_IP, self.NATHAN2_IP = "100.92.141.68", "100.93.161.73", "100.122.120.65"
        self.my_name, self.peer_name = None, None
        self.config_file = os.path.join(app_data_dir, "config.json")
        self.chat_history_file = os.path.join(app_data_dir, "chat_history.log")
        self.downloads_folder = os.path.join(app_data_dir, "Vortex_Downloads")
        os.makedirs(self.downloads_folder, exist_ok=True)
        self.file_gallery_metadata_file = os.path.join(
            app_data_dir, "file_gallery.json")

        self.host_ip_listen, self.port = "0.0.0.0", 12345
        self.server_socket = None  # Keep a reference to the server socket
        # Keep a reference to the client socket (for outgoing connection)
        self.client_socket = None
        self.connection, self.connected = None, threading.Event()
        self.pending_transfers = {}  # Stores info about files being sent/received
        self.chat_messages = {}
        self.file_gallery_items_metadata = {}  # {file_id: {filename, local_path}}
        self.file_gallery_widgets = {}  # {file_id: CTkFrame_widget}

        # Connection history for dropdown
        self.connection_history = {}  # Format: {ip: name}
        self.default_connections = {
            self.NATHAN_IP: self.NATHAN_NAME,
            self.MAJID_IP: self.MAJID_NAME,
            self.NATHAN2_IP: self.NATHAN2_NAME
        }

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

        # Create IP combobox with connection history
        self.ip_combobox = ctk.CTkComboBox(
            top_frame,
            values=["Enter IP to connect..."],
            font=ctk.CTkFont(size=14),
            command=self.on_ip_selection
        )
        self.ip_combobox.pack(side="left", padx=5,
                              pady=5, expand=True, fill="x")
        self.ip_combobox.set("Enter IP to connect...")

        self.connect_button = ctk.CTkButton(top_frame, text="Connect", font=ctk.CTkFont(
            size=14), command=self.connect_to_peer)
        self.connect_button.pack(side="left", padx=5, pady=5)
        self.settings_button = ctk.CTkButton(
            top_frame, text="⚙️", width=30, font=ctk.CTkFont(size=18), command=self.open_settings)
        self.settings_button.pack(side="left", padx=5, pady=5)
        self.pin_button = ctk.CTkButton(top_frame, text="📌", width=30, font=ctk.CTkFont(
            size=18), command=self.toggle_topmost)
        self.pin_button.pack(side="left", padx=5, pady=5)
        self.is_pinned = False

        self.tab_view = ctk.CTkTabview(self.main_container_frame)
        self.tab_view.grid(row=1, column=0, padx=0,
                           pady=(0, 10), sticky="nsew")

        self.tab_view.add("Files")
        self.tab_view.add("Drawing")
        self.tab_view.add("Chat")

        self._create_files_tab()
        self._create_drawing_tab()
        self._create_chat_tab()

        self.tab_view.set("Files")

        bottom_frame = ctk.CTkFrame(self.main_container_frame)
        bottom_frame.grid(row=2, column=0, padx=0, pady=(0, 10), sticky="ew")

        profile_options = [
            "Select Profile", f"I am {self.NATHAN_NAME}", f"I am {self.MAJID_NAME}", f"I am {self.NATHAN2_NAME}"]
        self.profile_menu = ctk.CTkOptionMenu(
            bottom_frame, values=profile_options, font=ctk.CTkFont(size=14), command=self.profile_selected)
        self.profile_menu.pack(side="left", padx=5, pady=5)
        self.status_label = ctk.CTkLabel(
            bottom_frame, text="Status: Disconnected", text_color="white", font=ctk.CTkFont(size=14))
        self.status_label.pack(side="left", padx=10, pady=5)

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

        self.clear_chat_button = ctk.CTkButton(input_frame, text="Clear Chat", font=ctk.CTkFont(
            size=14), command=self.confirm_clear_chat)
        self.clear_chat_button.grid(row=0, column=2, padx=5, pady=5)

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
        self.last_mouse_move_time = 0  # Initialize the timer

        # Bind drawing events
        self.canvas.bind("<Button-1>", self.start_drawing)
        self.canvas.bind("<B1-Motion>", self.draw)
        self.canvas.bind("<ButtonRelease-1>", self.reset_drawing_state)

        # Bind mouse tracking events
        self.canvas.bind("<Motion>", self.send_mouse_position)
        self.canvas.bind("<Leave>", self.send_mouse_leave)

        self.canvas.after(100, self.check_remote_mouse_timeout)

    def _create_files_tab(self):
        files_tab = self.tab_view.tab("Files")
        files_tab.grid_columnconfigure(0, weight=1)
        files_tab.grid_rowconfigure(0, weight=1)

        # Create a main container frame
        main_container = ctk.CTkFrame(files_tab, fg_color="transparent")
        main_container.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        main_container.grid_columnconfigure(0, weight=1)
        main_container.grid_rowconfigure(0, weight=1)

        self.gallery_frame = ctk.CTkScrollableFrame(
            main_container, label_text="Shared File Gallery")
        self.gallery_frame.grid(row=0, column=0, sticky="nsew")

        # Enable drag and drop for relevant widgets
        # Bind to master for global drop
        self.master.dnd_bind('<<Drop>>', self.handle_drop)
        self.master.drop_target_register(DND_FILES)

        files_tab.dnd_bind('<<Drop>>', self.handle_drop)
        files_tab.drop_target_register(DND_FILES)
        main_container.dnd_bind('<<Drop>>', self.handle_drop)
        main_container.drop_target_register(DND_FILES)
        self.gallery_frame.dnd_bind('<<Drop>>', self.handle_drop)
        self.gallery_frame.drop_target_register(DND_FILES)
        self.chat_entry.dnd_bind('<<Drop>>', self.handle_drop)
        self.chat_entry.drop_target_register(DND_FILES)

        for i in range(4):
            self.gallery_frame.grid_columnconfigure(
                i, weight=1, uniform="file_item")

        # Create drag & drop label that goes below the file containers
        self.drag_drop_label = ctk.CTkLabel(
            main_container,
            text="Drag & Drop Files Here",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color="gray50"
        )
        self.drag_drop_label.grid(row=1, column=0, pady=20)

        # Also enable drag and drop for the label itself
        self.drag_drop_label.drop_target_register(DND_FILES)
        self.drag_drop_label.dnd_bind('<<Drop>>', self.handle_drop)

        self._update_drag_drop_label_visibility()

    def _update_drag_drop_label_visibility(self):
        """Manages the visibility of the 'Drag & Drop Files Here' label."""
        # Use metadata count, not widget count, as widgets are created when metadata is loaded
        if not self.file_gallery_items_metadata:
            self.drag_drop_label.lift()
            self.drag_drop_label.configure(text_color="gray50")
            print("DEBUG: Drag & Drop label visible (no files).")
        else:
            self.drag_drop_label.lower()
            self.drag_drop_label.configure(text_color="transparent")
            print("DEBUG: Drag & Drop label hidden (files present).")
        self.gallery_frame.update_idletasks()  # Ensure UI updates

    def open_settings(self):
        SettingsDialog(self.master, self)

    def choose_color(self):
        color_code = colorchooser.askcolor(title="Choose color")
        self.color = color_code[1] if color_code else self.color

    def toggle_topmost(self):
        self.is_pinned = not self.is_pinned
        self.master.attributes("-topmost", self.is_pinned)
        self.pin_button.configure(
            fg_color=("#3b8ed0", "#1f6aa5") if self.is_pinned else ctk.ThemeManager.theme["CTkButton"]["fg_color"])

    def handle_drop(self, event):
        try:
            print(f"DEBUG: Raw event data: '{event.data}'")
            # tkinterdnd2 often wraps paths in curly braces or provides multiple paths
            paths = self.master.tk.splitlist(event.data)
            filepath = None

            if paths:
                # Take the first path for simplicity, assuming single file drag and drop
                raw_path = paths[0]
                print(f"DEBUG: Extracted raw_path: '{raw_path}'")

                # Clean up path: remove potential leading/trailing quotes and handle backslashes
                # This is crucial for Windows paths
                if raw_path.startswith('{') and raw_path.endswith('}'):
                    raw_path = raw_path[1:-1]
                if raw_path.startswith('"') and raw_path.endswith('"'):
                    raw_path = raw_path[1:-1]

                # Ensure consistent path separators, especially important for os.path.exists
                if os.name == 'nt':  # On Windows, replace forward slashes with backslashes
                    filepath = raw_path.replace('/', '\\')
                else:
                    filepath = raw_path  # On Linux/macOS, forward slashes are fine

            print(f"DEBUG: Processed filepath: '{filepath}'")

            if filepath and os.path.exists(filepath) and os.path.isfile(filepath):
                print(f"DEBUG: File exists, calling send_file for: {filepath}")
                result = self.send_file(filepath)
                if result is not False:  # send_file returns False on error
                    self.update_status(
                        f"Initiated file transfer for: {os.path.basename(filepath)}", "white")
                    print(
                        f"DEBUG: Successfully initiated file send for: {filepath}")
                else:
                    self.update_status(
                        "Failed to initiate file transfer.", "red")
            else:
                error_msg = f"Invalid file path or not a file: '{filepath}'" if filepath else "Could not extract file path from drop event."
                print(f"ERROR: {error_msg}")
                self.update_status("Invalid file or path not found.", "red")

        except Exception as e:
            print(f"ERROR: Exception in handle_drop: {e}")
            import traceback
            traceback.print_exc()
            self.update_status("Error processing dropped file.", "red")

    def add_chat_message(self, msg_id, sender, message, is_own, is_file=False, file_info=None):
        if msg_id in self.chat_messages:
            # If message with this ID already exists, update it instead of adding new
            row_frame = self.chat_messages[msg_id]
            # Find the message label/frame and update its text/content
            for widget in row_frame.winfo_children():
                if isinstance(widget, ctk.CTkFrame):  # This is the msg_frame
                    for inner_widget in widget.winfo_children():
                        if isinstance(inner_widget, ctk.CTkLabel) and not inner_widget.cget("text").startswith(f"{sender}:"):
                            inner_widget.configure(text=message)
                            break
            print(f"DEBUG: Updated chat message with ID: {msg_id}")
            self.after(100, self.chat_frame._parent_canvas.yview_moveto, 1.0)
            return

        row_frame = ctk.CTkFrame(self.chat_frame, fg_color="transparent")
        row_frame.pack(fill="x", padx=5, pady=2)
        # Makes the message expand to the correct side
        row_frame.grid_columnconfigure(1 if is_own else 0, weight=1)

        msg_frame = ctk.CTkFrame(row_frame)
        msg_frame.grid(row=0, column=1 if is_own else 0,
                       sticky="e" if is_own else "w")

        # Sender label (e.g., "Majid:")
        ctk.CTkLabel(msg_frame, text=f"{sender}:", font=ctk.CTkFont(
            weight="bold", size=14)).pack(side="left", padx=(10, 5), pady=5)

        if is_file:
            file_name_display = file_info.get('name', 'Unknown File')
            file_size_display = file_info.get('size', 0)
            file_size_mb = file_size_display / \
                (1024 * 1024) if file_size_display else 0

            file_frame = ctk.CTkFrame(msg_frame, fg_color="gray20")
            file_frame.pack(side="left", padx=5, pady=5)
            ctk.CTkLabel(file_frame, text=f"📄 {file_name_display}", wraplength=150, font=ctk.CTkFont(
                size=14)).pack(anchor="w")
            ctk.CTkLabel(file_frame, text=f"Size: {file_size_mb:.2f} MB", font=(
                "Arial", 11)).pack(anchor="w")

            # If it's *our* sent file, the download button might not be needed or should be "Open"
            # For now, keep it as download, but it would just open the local file
            if not is_own:  # Only show download for received files, not our own sent files
                ctk.CTkButton(file_frame, text="Download", font=ctk.CTkFont(
                    size=14), command=lambda id=file_info['id'], name=file_info['name']: self.request_file_download(id, name)).pack(pady=5)
            else:
                # For self-sent files, maybe an "Open Locally" button or just a status
                ctk.CTkLabel(file_frame, text="Sent", font=ctk.CTkFont(
                    size=12, slant="italic")).pack(pady=5)

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
        if not self.connected.is_set():
            self.update_status("Not connected to a peer.", "red")
            messagebox.showwarning(
                "Connection Required", "Please connect to a peer before sending messages.")
            return

        cmd = "EDIT_MSG" if msg_id_to_edit else "CHAT_MSG"
        msg_id = msg_id_to_edit if msg_id_to_edit else str(uuid.uuid4())
        full_command = f"{cmd}:{msg_id}:{self.my_name}:{msg}"
        self.send_command(full_command)
        self.process_command(full_command)  # Process locally immediately
        self.chat_entry.delete(0, tk.END)
        if msg_id_to_edit:
            self.send_button.configure(
                text="Send", command=self.send_chat_message)

    def edit_chat_prompt(self, msg_id):
        if msg_id not in self.chat_messages:
            return

        row_frame = self.chat_messages[msg_id]
        # The inner frame containing sender and message
        msg_frame = row_frame.winfo_children()[0]

        # Find the message label within the msg_frame
        original_text = ""
        for widget in msg_frame.winfo_children():
            if isinstance(widget, ctk.CTkLabel) and not widget.cget("text").endswith(":") and "Size:" not in widget.cget("text"):
                original_text = widget.cget("text")
                break

        if original_text:
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
            # The actual clearing happens in process_command.
            # We don't need to call process_command("CLEAR_CHAT") directly here,
            # as it will be received back from our own send_command.
            self.update_status("Chat clear requested!", "white")

    def _create_gallery_item_widget(self, file_id, filename, local_path):
        """Creates and stores the CTkFrame widget for a file gallery item."""
        print(
            f"DEBUG: _create_gallery_item_widget called for ID: {file_id}, Filename: {filename}")

        # If widget already exists (e.g., re-drawing), destroy it before recreating
        if file_id in self.file_gallery_widgets:
            self.file_gallery_widgets[file_id].destroy()
            del self.file_gallery_widgets[file_id]

        file_frame = ctk.CTkFrame(
            self.gallery_frame, width=150, height=150, corner_radius=10, fg_color="gray15")
        file_frame.grid_propagate(False)

        img_label = None
        try:
            # Check if it's an image file for thumbnail generation
            if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico')):
                img = Image.open(local_path)
                img.thumbnail((96, 96))
                thumb_img = ImageTk.PhotoImage(img)
                img_label = ctk.CTkLabel(file_frame, image=thumb_img, text="")
                img_label.image = thumb_img  # Keep a reference!
                img_label.pack(pady=(10, 5))
            else:
                # Default icon for non-image files
                img_label = ctk.CTkLabel(file_frame, text="📄", font=("Arial", 48), width=96, height=96,
                                         fg_color="gray25", corner_radius=6)
                img_label.pack(pady=(10, 5))
        except Exception as e:
            print(
                f"WARNING: Could not generate thumbnail for {filename}: {e}. Using default icon.")
            img_label = ctk.CTkLabel(file_frame, text="📄", font=("Arial", 48), width=96, height=96,
                                     fg_color="gray25", corner_radius=6)
            img_label.pack(pady=(10, 5))

        ctk.CTkLabel(file_frame, text=filename, wraplength=120, justify="center",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(0, 0))

        file_type = os.path.splitext(filename)[1].upper()[1:] or "FILE"
        if not file_type:
            file_type = "FILE"
        ctk.CTkLabel(file_frame, text=file_type, font=(
            "Arial", 11, "italic"), text_color="gray").pack(pady=(0, 5))

        button_frame = ctk.CTkFrame(file_frame, fg_color="transparent")
        button_frame.pack(pady=(0, 10), padx=10)

        # "Download" button for files received from peer, "Open" for local files
        if local_path.startswith(self.downloads_folder):  # This file was downloaded
            ctk.CTkButton(button_frame, text="Open", width=70, height=25, font=ctk.CTkFont(size=14),
                          command=lambda p=local_path: os.startfile(p) if os.name == 'nt' else os.system(f'xdg-open "{p}"') if sys.platform == 'linux' else os.system(f'open "{p}"')).pack(side="left", padx=(0, 2))
        else:  # This file was sent by me, or is a local file I added
            ctk.CTkButton(button_frame, text="Request", width=70, height=25, font=ctk.CTkFont(size=14),
                          command=lambda id=file_id, name=filename: self.request_file_download(id, name)).pack(side="left", padx=(0, 2))

        ctk.CTkButton(button_frame, text="Delete", width=70, height=25, fg_color="#D32F2F", hover_color="#B71C1C", font=ctk.CTkFont(size=14),
                      command=lambda id=file_id, path=local_path: self.confirm_delete_file(id, path)).pack(side="right", padx=(2, 0))

        self.file_gallery_widgets[file_id] = file_frame
        print(f"DEBUG: Widget created for {filename}.")

    def add_file_to_gallery(self, file_id, filename, local_path):
        print(
            f"DEBUG: add_file_to_gallery called for ID: {file_id}, Filename: {filename}, Path: {local_path}")

        if not os.path.exists(local_path):
            print(
                f"ERROR: File not found at {local_path}, skipping gallery addition.")
            # Do not return, as the file might be added by peer (they would have it)
            # In such cases, we store metadata but the 'open'/'request' action needs attention
            # For now, we allow metadata storage even if local file is missing, for consistency.

        # Store metadata
        self.file_gallery_items_metadata[file_id] = {
            "file_id": file_id,
            "filename": filename,
            "local_path": local_path
        }

        # Create the widget for the new file
        self._create_gallery_item_widget(file_id, filename, local_path)

        # Save metadata and rearrange grid after adding
        self._save_file_gallery_metadata()
        self._update_drag_drop_label_visibility()
        # Recalculate and place all widgets to ensure correct grid layout
        self._rearrange_gallery_grid()
        self.gallery_frame.update_idletasks()
        print(
            f"DEBUG: File {filename} (ID: {file_id}) added to gallery. Total widgets: {len(self.file_gallery_widgets)}")

    def _rearrange_gallery_grid(self):
        """Rearranges all file widgets in the gallery frame into a grid."""
        print("DEBUG: _rearrange_gallery_grid called.")
        # Clear existing grid layout for all widgets in gallery_frame
        for widget in self.gallery_frame.winfo_children():
            # Only forget actual file frames, not the drag_drop_label which is in main_container
            # or the scrollbar itself if _create_files_tab changes its structure
            if isinstance(widget, ctk.CTkFrame) and widget in self.file_gallery_widgets.values():
                widget.grid_forget()

        row, col = 0, 0
        # Iterate through the ordered metadata to maintain consistent display order
        for file_id in self.file_gallery_items_metadata:
            if file_id in self.file_gallery_widgets:  # Only try to grid if widget exists
                file_frame = self.file_gallery_widgets[file_id]
                file_frame.grid(row=row, column=col, padx=10,
                                pady=10, sticky="nsew")
                col += 1
                if col >= 4:  # 4 columns per row
                    col = 0
                    row += 1
        print(
            f"DEBUG: Rearranged {len(self.file_gallery_widgets)} widgets in gallery grid.")
        self.gallery_frame.update_idletasks()  # Force update
        self._update_drag_drop_label_visibility()

    def send_file(self, filepath):
        if not filepath or not os.path.exists(filepath):
            print(
                f"ERROR: Cannot send file. Path invalid or doesn't exist: {filepath}")
            self.update_status("Invalid file path.", "red")
            return False

        if not self.connected.is_set() or self.connection is None:
            self.update_status(
                "Cannot send file: Not connected to peer.", "red")
            messagebox.showwarning(
                "Connection Required", "Please connect to a peer before sending files.")
            return False

        try:
            filename = os.path.basename(filepath)
            filesize = os.path.getsize(filepath)
            file_id = str(uuid.uuid4())

            # Store the file in pending transfers, indicating it's *our* file to send
            self.pending_transfers[file_id] = {
                "filepath": filepath,
                "filename": filename,
                "filesize": filesize,
                "direction": "send"  # Mark as sending
            }

            # Add to gallery immediately locally
            self.add_file_to_gallery(file_id, filename, filepath)

            self.update_status(f"Requesting to send '{filename}'...", "orange")
            # Send the file request (this is just metadata, no actual file data yet)
            self.send_command(f"FILE_REQUEST:{file_id}:{filename}:{filesize}")

            # Set a timeout to clear the status if no response
            self.after(10000, lambda: self._check_file_transfer_timeout(
                file_id, filename))

            print(
                f"DEBUG: Initiated file transfer request for {filename} (ID: {file_id}).")
            return True

        except Exception as e:
            print(f"ERROR: Exception in send_file: {e}")
            self.update_status(
                f"Failed to initiate file send: {str(e)}", "red")
            return False

    def _check_file_transfer_timeout(self, file_id, filename):
        """Check if a file transfer request has timed out"""
        if file_id in self.pending_transfers and self.pending_transfers[file_id].get("direction") == "send":
            # Still pending for sending, means the peer didn't respond to FILE_REQUEST
            del self.pending_transfers[file_id]
            self.update_status(
                f"File transfer request for '{filename}' timed out. Peer did not accept.", "red")
            print(
                f"DEBUG: File transfer timeout for {filename} (ID: {file_id})")

    def _send_file_data(self, file_id):
        """Sends the actual file data after FILE_ACCEPT is received."""
        if file_id not in self.pending_transfers or self.pending_transfers[file_id].get("direction") != "send":
            print(
                f"DEBUG: File ID {file_id} not found or not a pending send transfer. Aborting send_file_data.")
            return

        filepath = self.pending_transfers[file_id]['filepath']
        filename = self.pending_transfers[file_id]['filename']
        filesize = self.pending_transfers[file_id]['filesize']

        try:
            with open(filepath, 'rb') as f:
                # Send a command indicating actual data transfer is starting
                # This helps the receiver prepare for raw byte stream
                # No filename/filesize needed here, already sent in FILE_REQUEST
                self.send_command(f"FILE_START_TRANSFER:{file_id}")

                self.update_status(
                    f"Sending '{filename}' ({filesize / (1024*1024):.2f} MB)...", "cyan")
                print(
                    f"DEBUG: Starting actual file data transfer for {filename} (ID: {file_id}).")

                bytes_sent = 0
                while True:
                    chunk = f.read(4096)  # Read in chunks
                    if not chunk:
                        break  # End of file
                    if not self.connected.is_set() or self.connection is None:
                        raise ConnectionError(
                            "Connection lost during file data transfer.")

                    # Send the chunk length first, then the chunk
                    # Pack length as a 4-byte unsigned int (Network byte order)
                    length_prefix = struct.pack("!I", len(chunk))
                    self.connection.sendall(length_prefix + chunk)
                    bytes_sent += len(chunk)

                    # Update status periodically (e.g., every 1MB)
                    # Update roughly every 1MB
                    if bytes_sent % (1024 * 1024) < 4096 and bytes_sent > 0:
                        self.update_status(
                            f"Sending '{filename}': {bytes_sent / (1024*1024):.2f}/{filesize / (1024*1024):.2f} MB", "cyan")

            # Signal end of transfer
            self.send_command(f"FILE_END_TRANSFER:{file_id}")
            self.update_status(f"Successfully sent '{filename}'.", "green")
            print(
                f"DEBUG: Completed file data transfer for {filename} (ID: {file_id}).")

            # After successful send, tell the peer to add it to their gallery
            # The peer will already have the file details from FILE_REQUEST, just needs confirmation to add
            # This is important to ensure both galleries are in sync.
            self.send_command(f"ADD_TO_GALLERY:{file_id}:{filename}")

        except ConnectionError as ce:
            self.update_status(
                f"Connection lost while sending '{filename}': {ce}", "red")
            print(f"ERROR: Connection error during _send_file_data: {ce}")
            messagebox.showerror("File Transfer Error",
                                 f"Connection lost while sending '{filename}'.")
        except Exception as e:
            print(f"ERROR: Exception sending file data for {filename}: {e}")
            self.update_status(f"Failed to send '{filename}': {str(e)}", "red")
            messagebox.showerror("File Transfer Error",
                                 f"Failed to send '{filename}': {e}")
        finally:
            # Clean up pending transfer, regardless of success or failure
            if file_id in self.pending_transfers:
                del self.pending_transfers[file_id]
                print(f"DEBUG: Cleaned up pending transfer for {file_id}.")

    def request_file_download(self, file_id, filename):
        if not self.connected.is_set():
            self.update_status(
                "Cannot request download: Not connected to peer.", "red")
            messagebox.showwarning("Connection Required",
                                   "Please connect to a peer to request files.")
            return

        if file_id not in self.file_gallery_items_metadata:
            self.update_status(
                f"File '{filename}' (ID: {file_id}) not found in your gallery. Cannot request.", "red")
            print(
                f"WARNING: Attempted to request download for unknown file ID: {file_id}")
            return

        self.update_status(
            f"Requested download of '{filename}' from peer...", "orange")
        self.send_command(f"REQUEST_DOWNLOAD:{file_id}:{filename}")
        print(
            f"DEBUG: Sent REQUEST_DOWNLOAD for file ID: {file_id}, Filename: {filename}")

        # Add to pending transfers for receiving
        self.pending_transfers[file_id] = {
            "filename": filename,
            "direction": "receive",  # Mark as receiving
            "received_bytes": 0,
            "expected_filesize": 0,  # Will be updated by FILE_START_DOWNLOAD
            # Temporary file path
            "temp_file_path": os.path.join(self.downloads_folder, f"{file_id}_{filename}.part")
        }

    def _send_gallery_file_data(self, file_id, requester_filename):
        """Called by peer when they request a file from our gallery."""
        if file_id not in self.file_gallery_items_metadata:
            print(
                f"ERROR: Cannot send gallery file. ID {file_id} not found in our gallery.")
            self.send_command(
                f"FILE_DENY:{file_id}:File not found in sender's gallery.")
            return

        file_info = self.file_gallery_items_metadata[file_id]
        filepath = file_info["local_path"]
        filename = file_info["filename"]  # Use actual filename from metadata
        filesize = os.path.getsize(filepath)

        if not os.path.exists(filepath):
            print(
                f"ERROR: Local file missing for gallery item ID {file_id} at {filepath}.")
            self.send_command(
                f"FILE_DENY:{file_id}:Sender's file missing locally.")
            return

        try:
            # First, send metadata so receiver knows what to expect
            self.send_command(
                f"FILE_START_DOWNLOAD:{file_id}:{filename}:{filesize}")

            with open(filepath, 'rb') as f:
                self.update_status(
                    f"Sending gallery file '{filename}' to peer...", "cyan")
                print(
                    f"DEBUG: Starting transfer of gallery file {filename} (ID: {file_id}).")

                while True:
                    chunk = f.read(4096)
                    if not chunk:
                        break
                    if not self.connected.is_set() or self.connection is None:
                        raise ConnectionError(
                            "Connection lost during gallery file transfer.")

                    length_prefix = struct.pack("!I", len(chunk))
                    self.connection.sendall(length_prefix + chunk)

            self.send_command(f"FILE_END_TRANSFER:{file_id}")
            self.update_status(
                f"Successfully sent gallery file '{filename}'.", "green")
            print(
                f"DEBUG: Completed sending gallery file {filename} (ID: {file_id}).")

        except ConnectionError as ce:
            self.update_status(
                f"Connection lost while sending gallery file '{filename}': {ce}", "red")
            print(
                f"ERROR: Connection error during _send_gallery_file_data: {ce}")
            messagebox.showerror(
                "File Transfer Error", f"Connection lost while sending gallery file '{filename}'.")
        except Exception as e:
            print(
                f"ERROR: Exception sending gallery file data for {filename}: {e}")
            self.update_status(
                f"Failed to send gallery file '{filename}': {str(e)}", "red")
            messagebox.showerror(
                "File Transfer Error", f"Failed to send gallery file '{filename}': {e}")
        finally:
            # No need to remove from pending_transfers here as it was a request from peer
            # and not an initiated 'send_file'
            pass

    def confirm_delete_file(self, file_id, local_path):
        filename = self.file_gallery_items_metadata.get(
            file_id, {}).get("filename", "this file")
        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete '{filename}' from your gallery and send a delete request to the peer? This will delete the local file as well."):
            self.send_command(f"DELETE_FILE:{file_id}")
            # Process locally immediately
            self.process_command(f"DELETE_FILE:{file_id}")

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
            print(f"DEBUG: Saved {len(files_to_save)} files to metadata.")
        except Exception as e:
            print(f"Error saving file gallery metadata: {e}")

    def load_config_and_history(self):
        print("DEBUG: Loading config and history...")
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                last_profile_name = config.get("last_profile")
                if last_profile_name and last_profile_name != "Select Profile":
                    # Find the exact string from profile_options to set
                    for option in self.profile_menu._values:
                        if last_profile_name in option:
                            self.profile_menu.set(option)
                            # Call handler to set self.my_name etc.
                            self.profile_selected(option)
                            break
                    print(f"DEBUG: Loaded last profile: {last_profile_name}")

                # Load connection history
                self.connection_history = config.get("connection_history", {})
                print(
                    f"DEBUG: Loaded {len(self.connection_history)} connection history entries")

            # Update IP dropdown with loaded history and defaults
            self.update_ip_dropdown()

            if os.path.exists(self.chat_history_file):
                # Clear existing chat messages before loading from history
                for w in list(self.chat_messages.values()):
                    w.destroy()
                self.chat_messages.clear()
                with open(self.chat_history_file, 'r') as f:
                    for line in f:
                        self.process_command(line.strip(), from_history=True)
                print(
                    f"DEBUG: Loaded chat history from {self.chat_history_file}")

            # Load file gallery metadata and build widgets
            if os.path.exists(self.file_gallery_metadata_file):
                with open(self.file_gallery_metadata_file, 'r') as f:
                    loaded_files = json.load(f)

                # Clear existing metadata and widgets before loading
                self.file_gallery_items_metadata.clear()
                for widget in list(self.file_gallery_widgets.values()):
                    widget.destroy()
                self.file_gallery_widgets.clear()

                for file_data in loaded_files:
                    # Validate that required keys exist
                    if all(k in file_data for k in ["file_id", "filename", "local_path"]):
                        file_id = file_data["file_id"]
                        filename = file_data["filename"]
                        local_path = file_data["local_path"]
                        # Only add if the file still physically exists on disk, or if it's a downloaded file that might be pending
                        if os.path.exists(local_path) or local_path.startswith(self.downloads_folder):
                            self.add_file_to_gallery(
                                file_id, filename, local_path)
                        else:
                            print(
                                f"WARNING: File {filename} (ID: {file_id}) referenced in gallery metadata does not exist at {local_path}. Skipping.")
                    else:
                        print(
                            f"WARNING: Invalid file entry in metadata: {file_data}")
                self._rearrange_gallery_grid()  # Re-grid after loading all
                self._update_drag_drop_label_visibility()
                print(
                    f"DEBUG: Loaded {len(self.file_gallery_items_metadata)} files into gallery.")
            else:
                print("DEBUG: No file gallery metadata found.")

            # Check for Nathan's auto-connect after loading profile
            if self.my_name == self.NATHAN_NAME:
                self.after(500, lambda: self.auto_connect_nathan())

        except json.JSONDecodeError as e:
            print(
                f"ERROR: Failed to decode JSON from config or history file: {e}")
            messagebox.showerror(
                "Load Error", f"Could not read configuration or history files. They might be corrupted. Error: {e}")
            # Optionally, back up corrupted files and start fresh
        except Exception as e:
            print(f"ERROR: Exception loading config and history: {e}")
            messagebox.showerror(
                "Load Error", f"An error occurred while loading settings: {e}")

    def _save_config(self):
        config = {
            "last_profile": self.profile_menu.get(),
            "connection_history": self.connection_history
        }
        try:
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=4)
            print("DEBUG: Config saved.")
        except Exception as e:
            print(f"Error saving config: {e}")

    def update_ip_dropdown(self):
        # Combine default connections and history, prioritize history for names
        combined_connections = {
            **self.default_connections, **self.connection_history}

        # Sort by name for better readability in dropdown
        sorted_connections = sorted(
            combined_connections.items(), key=lambda item: item[1])

        # Format for dropdown: "Name (IP)"
        dropdown_values = [f"{name} ({ip})" for ip, name in sorted_connections]

        # Add a placeholder if the list is empty or for initial state
        if not dropdown_values:
            dropdown_values = ["Enter IP to connect..."]

        # Set the values for the combobox
        self.ip_combobox.configure(values=dropdown_values)
        if self.ip_combobox.get() == "Enter IP to connect...":
            self.ip_combobox.set("Enter IP to connect...")

    def on_ip_selection(self, selection):
        # Extract IP from "Name (IP)" format
        if "(" in selection and ")" in selection:
            try:
                ip_part = selection.split('(')[-1].strip(')')
                # Validate if it's a plausible IP address
                if all(part.isdigit() for part in ip_part.split('.')) and len(ip_part.split('.')) == 4:
                    self.ip_combobox.set(ip_part)
                else:  # Fallback if it's not a valid IP string format
                    self.ip_combobox.set(selection)
            except Exception:
                # If parsing fails, just set the selection
                self.ip_combobox.set(selection)
        else:
            # If not in "Name (IP)" format, just set directly
            self.ip_combobox.set(selection)

    def profile_selected(self, choice):
        if "I am Nathan" in choice:
            self.my_name = self.NATHAN_NAME
            self.update_status(f"Profile set to {self.my_name}", "white")
            self._save_config()
            # If Nathan, auto-connect to Majid
            self.after(100, self.auto_connect_nathan)
        elif "I am Majid" in choice:
            self.my_name = self.MAJID_NAME
            self.update_status(f"Profile set to {self.my_name}", "white")
            self._save_config()
        elif "I am Majid 2.0" in choice:  # Assuming this is the 'Nathan2' profile
            self.my_name = self.NATHAN2_NAME
            self.update_status(f"Profile set to {self.my_name}", "white")
            self._save_config()
        else:
            self.my_name = None
            self.update_status("Profile not selected", "red")
            self._save_config()

    def auto_connect_nathan(self):
        if self.my_name == self.NATHAN_NAME and not self.connected.is_set():
            target_ip = self.MAJID_IP  # Nathan connects to Majid
            self.ip_combobox.set(target_ip)
            print(
                f"DEBUG: Nathan auto-connecting to {self.MAJID_NAME} ({target_ip})...")
            self.connect_to_peer()
        elif self.my_name == self.NATHAN_NAME and self.connected.is_set():
            print("DEBUG: Nathan is already connected, skipping auto-connect.")
        elif self.my_name != self.NATHAN_NAME:
            print("DEBUG: Not Nathan's profile, skipping auto-connect.")

    def start_server(self):
        if self.server_socket:
            print("Server already running.")
            return

        def _server_thread():
            self.server_socket = socket.socket(
                socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(
                socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                self.server_socket.bind((self.host_ip_listen, self.port))
                self.server_socket.listen(1)
                print(f"Listening on {self.host_ip_listen}:{self.port}")
                self.update_status(
                    f"Waiting for connection on port {self.port}...", "yellow")

                self.connection, addr = self.server_socket.accept()
                self.connected.set()
                self.peer_name = f"Peer@{addr[0]}"
                self.connection_history[addr[0]
                                        ] = self.peer_name  # Add to history
                self._save_config()
                self.update_ip_dropdown()
                print(f"Connected by {addr}")
                self.update_status(f"Connected to {self.peer_name}", "green")
                self.receive_data()

            except OSError as e:
                if "Address already in use" in str(e):
                    print(
                        f"ERROR: Port {self.port} is already in use. Retrying in 5 seconds...")
                    self.server_socket = None  # Clear it to allow re-creation
                    self.after(5000, self.start_server)
                else:
                    print(f"Server error: {e}")
                    self.update_status(f"Server error: {e}", "red")
                    self.disconnect()
            except Exception as e:
                print(f"Server thread crashed: {e}")
                self.update_status(f"Server error: {e}", "red")
                self.disconnect()

        threading.Thread(target=_server_thread, daemon=True).start()

    def connect_to_peer(self):
        if self.connected.is_set():
            print("Already connected. Disconnecting first.")
            self.disconnect()
            # Allow time for disconnect to fully process before reconnecting
            self.after(500, self.connect_to_peer)
            return

        peer_ip = self.ip_combobox.get().strip()

        # Check if the combobox text is a default placeholder
        if peer_ip == "Enter IP to connect...":
            messagebox.showwarning(
                "Connection Error", "Please enter a valid IP address or select from history.")
            return

        # Try to resolve name to IP if it's in "Name (IP)" format
        for ip, name in self.connection_history.items():
            if peer_ip == f"{name} ({ip})":
                peer_ip = ip
                break
        for ip, name in self.default_connections.items():
            if peer_ip == f"{name} ({ip})":
                peer_ip = ip
                break

        if not peer_ip or not self._is_valid_ip(peer_ip):
            messagebox.showwarning(
                "Invalid IP", "Please enter a valid IP address.")
            return

        def _connect_thread():
            self.client_socket = socket.socket(
                socket.AF_INET, socket.SOCK_STREAM)
            try:
                self.update_status(
                    f"Connecting to {peer_ip}:{self.port}...", "yellow")
                self.client_socket.connect((peer_ip, self.port))
                self.connection = self.client_socket
                self.connected.set()
                self.peer_name = f"Peer@{peer_ip}"
                # Add to history
                self.connection_history[peer_ip] = self.peer_name
                self._save_config()
                self.update_ip_dropdown()
                print(f"Connected to {peer_ip}")
                self.update_status(f"Connected to {self.peer_name}", "green")
                self.receive_data()
            except Exception as e:
                print(f"Connection error: {e}")
                self.update_status(f"Connection failed: {e}", "red")
                self.disconnect()  # Clean up any partial connection

        threading.Thread(target=_connect_thread, daemon=True).start()

    def _is_valid_ip(self, ip_str):
        parts = ip_str.split('.')
        return len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)

    def disconnect(self):
        if self.connected.is_set():
            self.connected.clear()
            # Attempt to send a disconnect message before closing
            try:
                if self.connection:
                    self.send_command("DISCONNECT_ACK:Bye", is_ack=True)
                    # Allow gracefull shutdown
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
            except OSError as e:
                print(f"Error during socket shutdown/close: {e}")
            finally:
                self.connection = None
                self.peer_name = None
                self.update_status("Status: Disconnected", "white")
                print("Disconnected.")

        if self.server_socket:
            try:
                self.server_socket.close()
            except OSError as e:
                print(f"Error closing server socket: {e}")
            finally:
                self.server_socket = None

        if self.client_socket:
            try:
                self.client_socket.close()
            except OSError as e:
                print(f"Error closing client socket: {e}")
            finally:
                self.client_socket = None

        # Clear any pending file transfers upon disconnect
        self.pending_transfers.clear()

    def send_command(self, command, is_ack=False):
        if not self.connected.is_set() or self.connection is None:
            if not is_ack:  # Don't print error for disconnect ACKs
                print(f"ERROR: Not connected. Cannot send command: {command}")
            return

        try:
            full_message = f"COMMAND:{command}".encode('utf-8')
            # Prefix message with its length for reliable transmission
            length_prefix = struct.pack("!I", len(full_message))
            self.connection.sendall(length_prefix + full_message)
            # print(f"DEBUG: Sent command: {command}")
        except Exception as e:
            print(f"ERROR: Failed to send command '{command}': {e}")
            self.update_status(f"Send error: {e}", "red")
            self.disconnect()  # Disconnect on send error

    def receive_data(self):
        def _receive_thread():
            buffer = b''
            message_length = 0
            header_size = 4  # Size of the length prefix (unsigned int)

            while self.connected.is_set() and self.connection:
                try:
                    # First, read the 4-byte length prefix
                    while len(buffer) < header_size:
                        packet = self.connection.recv(
                            header_size - len(buffer))
                        if not packet:
                            raise ConnectionResetError(
                                "Peer disconnected unexpectedly.")
                        buffer += packet

                    if message_length == 0:  # Only unpack if we haven't already
                        message_length = struct.unpack(
                            "!I", buffer[:header_size])[0]
                        buffer = buffer[header_size:]

                    # Now, read the actual message data
                    while len(buffer) < message_length:
                        packet = self.connection.recv(
                            min(4096, message_length - len(buffer)))
                        if not packet:
                            raise ConnectionResetError(
                                "Peer disconnected unexpectedly.")
                        buffer += packet

                    # Extract the full message
                    full_message = buffer[:message_length]
                    # Keep the rest in buffer for next message
                    buffer = buffer[message_length:]
                    message_length = 0  # Reset for the next message

                    decoded_message = full_message.decode(
                        'utf-8', errors='ignore')

                    if decoded_message.startswith("COMMAND:"):
                        command_str = decoded_message[len("COMMAND:"):]
                        self.process_command(command_str)
                    elif decoded_message.startswith("FILE_DATA_CHUNK:"):
                        # This should no longer happen with direct binary transfer
                        print("WARNING: Received old FILE_DATA_CHUNK. Ignoring.")
                    elif decoded_message.startswith("FILE_RAW_DATA:"):
                        # This should no longer happen if using length prefix correctly
                        print("WARNING: Received old FILE_RAW_DATA. Ignoring.")
                    else:
                        # If it's not a command, it's raw file data
                        self.handle_incoming_file_data(full_message)

                except struct.error:
                    print(
                        "ERROR: Incomplete message header received. Possibly corrupt data or lost sync.")
                    self.disconnect()
                    break
                except ConnectionResetError:
                    print("Peer disconnected.")
                    self.disconnect()
                    break
                except OSError as e:
                    if "Bad file descriptor" in str(e) or "WinError 10038" in str(e):
                        print(
                            "Socket already closed (likely due to disconnect). Exiting receive thread.")
                    else:
                        print(f"Socket error during receive: {e}")
                    self.disconnect()
                    break
                except Exception as e:
                    print(f"Error receiving data: {e}")
                    self.disconnect()
                    break
            print("Receive thread terminated.")

        threading.Thread(target=_receive_thread, daemon=True).start()

    def process_command(self, command_str, from_history=False):
        print(f"DEBUG: Processing command: {command_str}")
        if command_str.startswith("CHAT_MSG:"):
            parts = command_str.split(':', 3)
            if len(parts) == 4:
                msg_id, sender, message = parts[1], parts[2], parts[3]
                is_own = (sender == self.my_name)
                self.add_chat_message(msg_id, sender, message, is_own)
                if not from_history:
                    self._append_to_chat_history(command_str)
        elif command_str.startswith("EDIT_MSG:"):
            parts = command_str.split(':', 3)
            if len(parts) == 4:
                msg_id, sender, new_message = parts[1], parts[2], parts[3]
                # Update the existing message widget
                self.add_chat_message(
                    msg_id, sender, new_message, is_own=(sender == self.my_name))
                if not from_history:
                    self._update_chat_history(msg_id, command_str)
        elif command_str.startswith("DELETE_MSG:"):
            msg_id = command_str.split(':')[1]
            if msg_id in self.chat_messages:
                self.chat_messages[msg_id].destroy()
                del self.chat_messages[msg_id]
                self._update_chat_history_on_delete(msg_id)
            print(f"DEBUG: Deleted message {msg_id}")
        elif command_str == "CLEAR_CHAT":
            for w in list(self.chat_messages.values()):
                w.destroy()
            self.chat_messages.clear()
            if not from_history:
                self._clear_chat_history_file()
            self.update_status("Chat history cleared by peer!", "white")
        elif command_str.startswith("DRAWING:"):
            coords_str = command_str[len("DRAWING:"):]
            color, brush_size_str, x1_str, y1_str, x2_str, y2_str = coords_str.split(
                ',')
            brush_size = int(brush_size_str)
            x1, y1, x2, y2 = float(x1_str), float(
                y1_str), float(x2_str), float(y2_str)
            self.draw_remote(x1, y1, x2, y2, color, brush_size)
        elif command_str.startswith("MOUSE_MOVE:"):
            _, x, y, sender_name = command_str.split(':')
            self.update_remote_mouse(int(x), int(y), sender_name)
        elif command_str == "MOUSE_LEAVE":
            self.hide_remote_mouse()
        elif command_str == "CLEAR_CANVAS":
            self.canvas.delete("all")
            self.hide_remote_mouse()
            self.update_status("Canvas cleared by peer!", "white")
        elif command_str.startswith("FILE_REQUEST:"):
            _, file_id, filename, filesize_str = command_str.split(':')
            filesize = int(filesize_str)
            self.update_status(
                f"Received file request for '{filename}' ({filesize / (1024*1024):.2f} MB)...", "orange")

            # Ask user for permission to accept the file
            if messagebox.askyesno("File Transfer Request",
                                   f"Peer wants to send '{filename}' ({filesize / (1024*1024):.2f} MB). Do you accept?"):
                self.send_command(f"FILE_ACCEPT:{file_id}")
                self.update_status(
                    f"Accepted '{filename}'. Preparing to receive...", "cyan")
                # Prepare for receiving by adding to pending transfers
                self.pending_transfers[file_id] = {
                    "filename": filename,
                    "filesize": filesize,
                    "direction": "receive",
                    "received_bytes": 0,
                    "temp_file_path": os.path.join(self.downloads_folder, f"{file_id}_{filename}.part"),
                    # Direct to final name
                    "final_file_path": os.path.join(self.downloads_folder, filename)
                }
                # Create the temporary file immediately
                try:
                    with open(self.pending_transfers[file_id]["temp_file_path"], 'wb') as f:
                        pass  # Create empty file
                except Exception as e:
                    print(
                        f"ERROR: Could not create temp file {self.pending_transfers[file_id]['temp_file_path']}: {e}")
                    self.update_status(
                        f"Failed to create temp file for '{filename}'. Aborting.", "red")
                    self.send_command(
                        f"FILE_DENY:{file_id}:Receiver failed to create temp file.")
                    if file_id in self.pending_transfers:
                        del self.pending_transfers[file_id]

            else:
                self.send_command(
                    f"FILE_DENY:{file_id}:Receiver denied request.")
                self.update_status(
                    f"Denied transfer request for '{filename}'.", "white")
        elif command_str.startswith("FILE_ACCEPT:"):
            file_id = command_str.split(':')[1]
            if file_id in self.pending_transfers and self.pending_transfers[file_id].get("direction") == "send":
                filename = self.pending_transfers[file_id]['filename']
                self.update_status(
                    f"Peer accepted '{filename}'. Starting transfer...", "cyan")
                # Start sending the actual file data in a new thread
                threading.Thread(target=self._send_file_data,
                                 args=(file_id,), daemon=True).start()
            else:
                print(
                    f"WARNING: Received FILE_ACCEPT for unknown or non-pending send file ID: {file_id}")
        elif command_str.startswith("FILE_DENY:"):
            _, file_id, reason = command_str.split(':', 2)
            if file_id in self.pending_transfers:
                filename = self.pending_transfers[file_id]['filename']
                del self.pending_transfers[file_id]
                self.update_status(
                    f"File transfer for '{filename}' denied by peer. Reason: {reason}", "red")
            else:
                print(
                    f"WARNING: Received FILE_DENY for unknown file ID: {file_id}. Reason: {reason}")
        elif command_str.startswith("FILE_START_TRANSFER:"):
            file_id = command_str.split(':')[1]
            if file_id in self.pending_transfers and self.pending_transfers[file_id].get("direction") == "receive":
                filename = self.pending_transfers[file_id]['filename']
                filesize = self.pending_transfers[file_id]['filesize']
                self.update_status(
                    f"Receiving '{filename}' ({filesize / (1024*1024):.2f} MB)...", "cyan")
                print(
                    f"DEBUG: Peer is starting actual file data transfer for {filename} (ID: {file_id}).")
            else:
                print(
                    f"WARNING: Received FILE_START_TRANSFER for unknown or non-pending receive file ID: {file_id}")
        elif command_str.startswith("FILE_END_TRANSFER:"):
            file_id = command_str.split(':')[1]
            if file_id in self.pending_transfers and self.pending_transfers[file_id].get("direction") == "receive":
                transfer_info = self.pending_transfers[file_id]
                temp_path = transfer_info['temp_file_path']
                final_path = transfer_info['final_file_path']
                filename = transfer_info['filename']

                # Check if the received size matches expected size (optional, but good for integrity)
                actual_size = os.path.getsize(
                    temp_path) if os.path.exists(temp_path) else 0
                if actual_size != transfer_info['filesize']:
                    print(
                        f"WARNING: Received file size mismatch for {filename}. Expected {transfer_info['filesize']} but got {actual_size}.")
                    self.update_status(
                        f"Received '{filename}' but size mismatch! Check integrity.", "red")
                    # Optionally, rename with a warning or delete temp file

                # Rename the temporary file to its final name
                try:
                    if os.path.exists(temp_path):
                        # Handle potential existing file with same name
                        base, ext = os.path.splitext(final_path)
                        counter = 1
                        while os.path.exists(final_path):
                            final_path = f"{base} ({counter}){ext}"
                            counter += 1
                        os.rename(temp_path, final_path)
                        print(
                            f"DEBUG: Renamed temp file {temp_path} to {final_path}")
                        self.update_status(
                            f"Successfully received '{filename}'. Saved to downloads.", "green")
                        # Add to local gallery after successful receipt
                        self.add_file_to_gallery(
                            file_id, os.path.basename(final_path), final_path)
                    else:
                        print(
                            f"ERROR: Temp file for {filename} not found at {temp_path} on transfer end.")
                        self.update_status(
                            f"Failed to save '{filename}'. Temp file missing.", "red")
                except Exception as e:
                    print(f"ERROR: Failed to finalize file {filename}: {e}")
                    self.update_status(
                        f"Failed to save received file '{filename}': {e}", "red")
                finally:
                    del self.pending_transfers[file_id]
            else:
                print(
                    f"WARNING: Received FILE_END_TRANSFER for unknown or non-pending receive file ID: {file_id}")
        elif command_str.startswith("ADD_TO_GALLERY:"):
            _, file_id, filename = command_str.split(':', 2)
            # This command comes AFTER the file has been successfully transferred
            # We need to find the local path based on our downloads folder logic
            local_path = os.path.join(self.downloads_folder, filename)
            # If we received it already and it's in pending_transfers, its path is known
            if file_id in self.pending_transfers and self.pending_transfers[file_id].get("direction") == "receive":
                local_path = self.pending_transfers[file_id].get(
                    "final_file_path", local_path)

            # Only add to gallery if the file actually exists locally
            if os.path.exists(local_path):
                self.add_file_to_gallery(file_id, filename, local_path)
                self.update_status(
                    f"'{filename}' added to shared gallery.", "white")
            else:
                print(
                    f"WARNING: Received ADD_TO_GALLERY for {filename} (ID: {file_id}), but file not found locally at {local_path}. This might be an issue if the file transfer itself failed previously.")
                # We can still add metadata, but the "Open" button might not work.
                # For now, we only add if the file exists.
                # If we want to show a "missing file" icon, we'd add metadata without _create_gallery_item_widget
                # or create a special widget for missing files.

        elif command_str.startswith("REQUEST_DOWNLOAD:"):
            _, file_id, filename = command_str.split(':', 2)
            print(
                f"DEBUG: Received REQUEST_DOWNLOAD for file ID: {file_id}, Filename: {filename}")
            # Check if we have this file in our gallery
            if file_id in self.file_gallery_items_metadata:
                self.update_status(
                    f"Peer requested '{filename}' from your gallery. Sending...", "orange")
                # Send the file data in a new thread
                threading.Thread(target=self._send_gallery_file_data, args=(
                    file_id, filename), daemon=True).start()
            else:
                print(
                    f"WARNING: Peer requested download of file ID {file_id} ('{filename}') which is not in our gallery.")
                self.send_command(
                    f"FILE_DENY:{file_id}:File not found in sender's gallery.")
                self.update_status(
                    f"Denied peer's download request for '{filename}' (not found).", "red")

        elif command_str.startswith("DELETE_FILE:"):
            file_id = command_str.split(':')[1]
            if file_id in self.file_gallery_widgets:
                filename = self.file_gallery_items_metadata.get(
                    file_id, {}).get("filename", "unknown file")
                local_path = self.file_gallery_items_metadata.get(
                    file_id, {}).get("local_path")

                # Remove from UI
                self.file_gallery_widgets[file_id].destroy()
                del self.file_gallery_widgets[file_id]

                # Remove from metadata
                if file_id in self.file_gallery_items_metadata:
                    del self.file_gallery_items_metadata[file_id]

                # Delete local file if it exists and is in our downloads folder or original sent location
                # Be careful not to delete arbitrary user files. Only delete files that belong to Vortex Tunnel's management.
                if local_path and os.path.exists(local_path):
                    try:
                        # Only delete if it's in our downloads or if it's one of my *sent* files from appdata dir
                        if local_path.startswith(self.downloads_folder) or not local_path.startswith(os.getenv('APPDATA')):
                            os.remove(local_path)
                            print(f"DEBUG: Deleted local file: {local_path}")
                        else:
                            print(
                                f"WARNING: Not deleting local file {local_path} as it's outside managed folders.")
                    except OSError as e:
                        print(
                            f"ERROR: Could not delete local file {local_path}: {e}")

                self._save_file_gallery_metadata()
                self._rearrange_gallery_grid()
                self.update_status(
                    f"'{filename}' deleted from gallery.", "white")
                print(
                    f"DEBUG: File ID {file_id} deleted from gallery and locally (if applicable).")
            else:
                print(
                    f"WARNING: Received DELETE_FILE for unknown file ID: {file_id}")
        elif command_str.startswith("DISCONNECT_ACK:"):
            # Peer acknowledged disconnect, we don't need to do anything further than what disconnect() does
            print(
                f"DEBUG: Peer acknowledged disconnect: {command_str.split(':')[1]}")
            self.disconnect()  # Ensure full cleanup
        else:
            print(f"Unknown command: {command_str}")

    def handle_incoming_file_data(self, data_chunk):
        """Handles raw incoming bytes for file transfer."""
        # This function should only be called by the receive_data thread
        # after it has determined that the incoming data is raw file bytes,
        # not a command.

        # We need a way to know which file this data belongs to.
        # The current design uses a FILE_START_TRANSFER command with the file_id.
        # So, the 'pending_transfers' should already have an entry for a "receive" type.

        # Find the active receiving file. There should ideally only be one at a time.
        active_file_id = None
        for f_id, info in self.pending_transfers.items():
            if info.get("direction") == "receive":
                active_file_id = f_id
                break

        if active_file_id:
            transfer_info = self.pending_transfers[active_file_id]
            temp_path = transfer_info['temp_file_path']
            filename = transfer_info['filename']
            expected_filesize = transfer_info['filesize']

            try:
                with open(temp_path, 'ab') as f:  # Open in append-binary mode
                    f.write(data_chunk)

                transfer_info['received_bytes'] += len(data_chunk)
                # Update status periodically
                if transfer_info['received_bytes'] % (1024 * 1024) < len(data_chunk) and transfer_info['received_bytes'] > 0:
                    self.update_status(
                        f"Receiving '{filename}': {transfer_info['received_bytes'] / (1024*1024):.2f}/{expected_filesize / (1024*1024):.2f} MB", "cyan")

            except Exception as e:
                print(
                    f"ERROR: Error writing file data for {filename} to {temp_path}: {e}")
                self.update_status(
                    f"Error receiving '{filename}': {str(e)}", "red")
                if active_file_id in self.pending_transfers:
                    del self.pending_transfers[active_file_id]  # Clear state
                # Potentially send a FILE_DENY back to peer
        else:
            print(
                f"WARNING: Received unexpected raw file data. No active receiving file.")
            # This indicates a protocol desynchronization. Could log or disconnect.

    def _append_to_chat_history(self, command_str):
        try:
            with open(self.chat_history_file, 'a') as f:
                f.write(command_str + "\n")
        except Exception as e:
            print(f"Error appending to chat history: {e}")

    def _update_chat_history(self, msg_id, new_command_str):
        try:
            with open(self.chat_history_file, 'r') as f:
                lines = f.readlines()

            with open(self.chat_history_file, 'w') as f:
                found = False
                for line in lines:
                    if line.strip().startswith(f"CHAT_MSG:{msg_id}:") or line.strip().startswith(f"EDIT_MSG:{msg_id}:"):
                        f.write(new_command_str + "\n")
                        found = True
                    else:
                        f.write(line)
                if not found:  # If the message wasn't in history, append it
                    f.write(new_command_str + "\n")
        except Exception as e:
            print(f"Error updating chat history: {e}")

    def _update_chat_history_on_delete(self, msg_id):
        try:
            with open(self.chat_history_file, 'r') as f:
                lines = f.readlines()

            with open(self.chat_history_file, 'w') as f:
                for line in lines:
                    if not (line.strip().startswith(f"CHAT_MSG:{msg_id}:") or line.strip().startswith(f"EDIT_MSG:{msg_id}:")):
                        f.write(line)
        except Exception as e:
            print(f"Error deleting from chat history: {e}")

    def _clear_chat_history_file(self):
        try:
            open(self.chat_history_file, 'w').close()  # Clear file contents
            print("DEBUG: Chat history file cleared.")
        except Exception as e:
            print(f"Error clearing chat history file: {e}")

    def update_status(self, message, color="white"):
        self.status_label.configure(
            text=f"Status: {message}", text_color=color)

    def start_drawing(self, event):
        if not self.connected.is_set():
            self.update_status("Not connected to a peer.", "red")
            return
        self.old_x, self.old_y = event.x, event.y

    def draw(self, event):
        if self.old_x and self.old_y and self.connected.is_set():
            self.canvas.create_line(
                self.old_x, self.old_y, event.x, event.y,
                fill=self.color, width=self.brush_size, capstyle=tk.ROUND, smooth=tk.TRUE
            )
            command = f"DRAWING:{self.color},{self.brush_size},{self.old_x},{self.old_y},{event.x},{event.y}"
            self.send_command(command)
            self.old_x, self.old_y = event.x, event.y

    def reset_drawing_state(self, event):
        self.old_x, self.old_y = None, None

    def draw_remote(self, x1, y1, x2, y2, color, brush_size):
        self.canvas.create_line(x1, y1, x2, y2,
                                fill=color, width=brush_size, capstyle=tk.ROUND, smooth=tk.TRUE)

    def clear_canvas(self):
        if messagebox.askyesno("Confirm", "Are you sure you want to clear the canvas for everyone?"):
            self.canvas.delete("all")
            self.send_command("CLEAR_CANVAS")
            self.update_status("Canvas cleared!", "white")

    def update_remote_mouse(self, x, y, sender_name):
        # Create a small red square to represent the remote cursor
        cursor_size = 8
        if self.remote_mouse_id:
            self.canvas.delete(self.remote_mouse_id)
            self.canvas.delete(self.remote_mouse_label_id)

        self.remote_mouse_id = self.canvas.create_rectangle(
            x - cursor_size, y - cursor_size, x + cursor_size, y + cursor_size,
            fill="red", outline="white"
        )
        self.remote_mouse_label_id = self.canvas.create_text(
            x + cursor_size + 5, y - cursor_size, anchor="nw",
            text=sender_name, fill="red", font=("Arial", 10, "bold")
        )
        self.last_mouse_move_time = time.time()
        self.canvas.lift(self.remote_mouse_id)
        self.canvas.lift(self.remote_mouse_label_id)

    def hide_remote_mouse(self):
        if self.remote_mouse_id:
            self.canvas.delete(self.remote_mouse_id)
            self.canvas.delete(self.remote_mouse_label_id)
            self.remote_mouse_id = None
            self.remote_mouse_label_id = None

    def send_mouse_position(self, event):
        if self.connected.is_set() and self.my_name:
            current_time = time.time()
            # Only send updates every 100ms to reduce network traffic
            if current_time - self.last_mouse_move_time > 0.1:
                command = f"MOUSE_MOVE:{event.x}:{event.y}:{self.my_name}"
                self.send_command(command)
                self.last_mouse_move_time = current_time

    def send_mouse_leave(self, event):
        if self.connected.is_set():
            self.send_command("MOUSE_LEAVE")

    def check_remote_mouse_timeout(self):
        # 2 seconds of inactivity
        if self.remote_mouse_id and (time.time() - self.last_mouse_move_time > 2):
            self.hide_remote_mouse()
            print("DEBUG: Remote mouse timed out and hidden.")
        # Check every 0.5 seconds
        self.canvas.after(500, self.check_remote_mouse_timeout)


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    root = TkinterDnD.Tk()  # Use TkinterDnD.Tk instead of ctk.CTk for drag and drop
    root.title(f"Vortex Tunnel {VERSION}")
    root.geometry("800x600")

    app = VortexTunnelApp(master=root)
    app.pack(fill="both", expand=True, padx=0, pady=0)

    # Ensure disconnect on window close
    root.protocol("WM_DELETE_WINDOW", app.disconnect)
    root.mainloop()
