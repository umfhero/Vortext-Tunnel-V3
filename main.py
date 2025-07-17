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
import sys # Import sys for resource_path helper

# --- Application Version ---
VERSION = "V0.1.5" 

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

        ctk.CTkLabel(self, text="Vortex Tunnel Settings", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=20)
        info_frame = ctk.CTkFrame(self); info_frame.pack(pady=10, padx=20, fill="x")
        ctk.CTkLabel(info_frame, text=f"Version: {VERSION}", font=ctk.CTkFont(size=14)).pack(anchor="w", padx=10)
        ctk.CTkLabel(info_frame, text=f"My Name: {self.app.my_name or 'Not Selected'}", font=ctk.CTkFont(size=14)).pack(anchor="w", padx=10)
        ctk.CTkLabel(info_frame, text=f"Peer Name: {self.app.peer_name or 'Not Connected'}", font=ctk.CTkFont(size=14)).pack(anchor="w", padx=10)
        
        ctk.CTkButton(self, text="Check for Updates", font=ctk.CTkFont(size=14)).pack(pady=10)
        ctk.CTkButton(self, text="Close", command=self.destroy_dialog, font=ctk.CTkFont(size=14)).pack(pady=10)

    def _on_close(self):
        if hasattr(self.master, 'attributes'):
            self.master.attributes('-alpha', 1.0)
        self.destroy()

    def destroy_dialog(self):
        self._on_close()

    def check_for_updates(self):
        messagebox.showinfo("Update Check", "You are on the latest version of Vortex Tunnel.")

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
        self.file_gallery_metadata_file = os.path.join(app_data_dir, "file_gallery.json")

        self.host_ip_listen, self.port = "0.0.0.0", 12345
        self.connection, self.connected = None, threading.Event()
        self.pending_transfers, self.chat_messages = {}, {}
        self.file_gallery_items_metadata = {} 
        self.file_gallery_widgets = {} 

        self._create_widgets()
        self.load_config_and_history()
        self.start_server()

    def _create_widgets(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        self.main_container_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container_frame.grid(row=0, column=0, rowspan=3, padx=30, pady=0, sticky="nsew")
        self.main_container_frame.grid_columnconfigure(0, weight=1)
        self.main_container_frame.grid_rowconfigure(1, weight=1)

        top_frame = ctk.CTkFrame(self.main_container_frame)
        top_frame.grid(row=0, column=0, padx=0, pady=10, sticky="ew") 
        
        self.ip_entry = ctk.CTkEntry(top_frame, placeholder_text="Enter IP to connect...", font=ctk.CTkFont(size=14)); self.ip_entry.pack(side="left", padx=5, pady=5, expand=True, fill="x")
        self.connect_button = ctk.CTkButton(top_frame, text="Connect", font=ctk.CTkFont(size=14), command=self.connect_to_peer); self.connect_button.pack(side="left", padx=5, pady=5)
        self.settings_button = ctk.CTkButton(top_frame, text="⚙️", width=30, font=ctk.CTkFont(size=18), command=self.open_settings); self.settings_button.pack(side="left", padx=5, pady=5)
        self.pin_button = ctk.CTkButton(top_frame, text="📌", width=30, font=ctk.CTkFont(size=18), command=self.toggle_topmost); self.pin_button.pack(side="left", padx=5, pady=5); self.is_pinned = False
        
        self.tab_view = ctk.CTkTabview(self.main_container_frame)
        self.tab_view.grid(row=1, column=0, padx=0, pady=(0,10), sticky="nsew") 
        
        self.tab_view.add("Files")
        self.tab_view.add("Drawing")
        self.tab_view.add("Chat")

        self._create_files_tab() 
        self._create_drawing_tab()
        self._create_chat_tab()
        
        self.tab_view.set("Files") 

        bottom_frame = ctk.CTkFrame(self.main_container_frame); 
        bottom_frame.grid(row=2, column=0, padx=0, pady=(0,10), sticky="ew") 
        
        profile_options = ["Select Profile", f"I am {self.NATHAN_NAME}", f"I am {self.MAJID_NAME}"]
        self.profile_menu = ctk.CTkOptionMenu(bottom_frame, values=profile_options, font=ctk.CTkFont(size=14), command=self.profile_selected); self.profile_menu.pack(side="left", padx=5, pady=5)
        self.status_label = ctk.CTkLabel(bottom_frame, text="Status: Disconnected", text_color="white", font=ctk.CTkFont(size=14)); self.status_label.pack(side="left", padx=10, pady=5)

    def _create_chat_tab(self):
        chat_tab = self.tab_view.tab("Chat")
        chat_tab.grid_columnconfigure(0, weight=1); chat_tab.grid_rowconfigure(0, weight=1)
        self.chat_frame = ctk.CTkScrollableFrame(chat_tab); self.chat_frame.grid(row=0, column=0, sticky="nsew")
        input_frame = ctk.CTkFrame(chat_tab, fg_color="transparent"); input_frame.grid(row=1, column=0, sticky="ew")
        input_frame.grid_columnconfigure(0, weight=1)
        
        self.chat_entry = ctk.CTkEntry(input_frame, placeholder_text="Type a message or drag a file here...", font=ctk.CTkFont(size=14)); self.chat_entry.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        self.chat_entry.bind("<Return>", lambda e: self.send_chat_message())
        self.send_button = ctk.CTkButton(input_frame, text="Send", font=ctk.CTkFont(size=14), command=self.send_chat_message); self.send_button.grid(row=0, column=1, padx=5, pady=5)

        self.clear_chat_button = ctk.CTkButton(input_frame, text="Clear Chat", font=ctk.CTkFont(size=14), command=self.confirm_clear_chat)
        self.clear_chat_button.grid(row=0, column=2, padx=5, pady=5)

    def _create_drawing_tab(self):
        draw_tab = self.tab_view.tab("Drawing")
        draw_tab.grid_columnconfigure(0, weight=1); draw_tab.grid_rowconfigure(1, weight=1)
        controls = ctk.CTkFrame(draw_tab); controls.grid(row=0, column=0, sticky="ew")
        self.color, self.brush_size = "#FFFFFF", 3
        
        ctk.CTkButton(controls, text="Color", font=ctk.CTkFont(size=14), command=self.choose_color).pack(side="left", padx=5, pady=5)
        ctk.CTkSlider(controls, from_=1, to=50, command=lambda v: setattr(self, 'brush_size', int(v))).pack(side="left", expand=True, fill="x")
        ctk.CTkButton(controls, text="Clear Canvas", font=ctk.CTkFont(size=14), command=self.clear_canvas).pack(side="right", padx=5, pady=5)
        
        self.canvas = tk.Canvas(draw_tab, bg="#1a1a1a", highlightthickness=0); self.canvas.grid(row=1, column=0, sticky="nsew")
        self.old_x, self.old_y = None, None
        self.remote_mouse = None  
        self.remote_mouse_id = None
        self.remote_mouse_label_id = None
        self.canvas.bind("<B1-Motion>", self.draw); self.canvas.bind("<ButtonRelease-1>", self.reset_drawing_state)
        self.canvas.bind("<Motion>", self.send_mouse_position)
        self.canvas.bind("<Leave>", self.send_mouse_leave)
        self.canvas.after(100, self.check_remote_mouse_timeout)

    def _create_files_tab(self):
        files_tab = self.tab_view.tab("Files")
        files_tab.grid_columnconfigure(0, weight=1); files_tab.grid_rowconfigure(0, weight=1)
        
        self.gallery_frame = ctk.CTkScrollableFrame(files_tab, label_text="Shared File Gallery")
        self.gallery_frame.grid(row=0, column=0, sticky="nsew")
        
        for i in range(4):
            self.gallery_frame.grid_columnconfigure(i, weight=1, uniform="file_item") 
        
        self.drag_drop_label = ctk.CTkLabel(
            self.gallery_frame, 
            text="Drag & Drop Files Here", 
            font=ctk.CTkFont(size=36, weight="bold"), 
            text_color="gray50" 
        )
        self.drag_drop_label.place(relx=0.5, rely=0.5, anchor="center") 
        
        self._update_drag_drop_label_visibility() 

    def _update_drag_drop_label_visibility(self):
        """Manages the visibility of the 'Drag & Drop Files Here' label."""
        if not self.file_gallery_items_metadata: 
            self.drag_drop_label.lift() 
            self.drag_drop_label.configure(text_color="gray50") 
            print("DEBUG: Drag & Drop label visible (no files).")
        else: 
            self.drag_drop_label.lower() 
            self.drag_drop_label.configure(text_color="transparent") 
            print("DEBUG: Drag & Drop label hidden (files present).")
        self.gallery_frame.update_idletasks() 

    def open_settings(self):
        SettingsDialog(self.master, self)

    def choose_color(self): color_code = colorchooser.askcolor(title="Choose color"); self.color = color_code[1] if color_code else self.color
    def toggle_topmost(self): self.is_pinned = not self.is_pinned; self.master.attributes("-topmost", self.is_pinned); self.pin_button.configure(fg_color=("#3b8ed0", "#1f6aa5") if self.is_pinned else ctk.ThemeManager.theme["CTkButton"]["fg_color"])
    def handle_drop(self, event): 
        filepath = self.master.tk.splitlist(event.data)[0]
        print(f"DEBUG: Dropped file: {filepath}")
        self.send_file(filepath)
    
    def add_chat_message(self, msg_id, sender, message, is_own, is_file=False, file_info=None):
        if msg_id in self.chat_messages: return
        row_frame = ctk.CTkFrame(self.chat_frame, fg_color="transparent"); row_frame.pack(fill="x", padx=5, pady=2)
        row_frame.grid_columnconfigure(1 if is_own else 0, weight=1)
        msg_frame = ctk.CTkFrame(row_frame); msg_frame.grid(row=0, column=1 if is_own else 0, sticky="e" if is_own else "w")
        
        ctk.CTkLabel(msg_frame, text=f"{sender}:", font=ctk.CTkFont(weight="bold", size=14)).pack(side="left", padx=(10, 5), pady=5)
        if is_file:
            file_frame = ctk.CTkFrame(msg_frame, fg_color="gray20"); file_frame.pack(side="left", padx=5, pady=5)
            ctk.CTkLabel(file_frame, text=f"📄 {file_info['name']}", wraplength=150, font=ctk.CTkFont(size=14)).pack(anchor="w")
            ctk.CTkLabel(file_frame, text=f"Size: {file_info['size']:.2f} MB", font=("Arial", 11)).pack(anchor="w")
            ctk.CTkButton(file_frame, text="Download", font=ctk.CTkFont(size=14), command=lambda id=file_info['id'], name=file_info['name']: self.request_file_download(id, name)).pack(pady=5)
        else:
            msg_label = ctk.CTkLabel(msg_frame, text=message, wraplength=self.winfo_width() - 250, justify="left", font=ctk.CTkFont(size=14)); msg_label.pack(side="left", padx=5, pady=5, expand=True, fill="x")
        if is_own and not is_file:
            btn_frame = ctk.CTkFrame(msg_frame, fg_color="transparent"); btn_frame.pack(side="right", padx=5, pady=5)
            ctk.CTkButton(btn_frame, text="✏️", width=20, font=ctk.CTkFont(size=18), command=lambda id=msg_id: self.edit_chat_prompt(id)).pack()
            ctk.CTkButton(btn_frame, text="🗑️", width=20, font=ctk.CTkFont(size=18), command=lambda id=msg_id: self.send_command(f"DELETE_MSG:{id}")).pack(pady=(2,0))
        self.chat_messages[msg_id] = row_frame
        self.after(100, self.chat_frame._parent_canvas.yview_moveto, 1.0)

    def send_chat_message(self, msg_id_to_edit=None):
        msg = self.chat_entry.get();
        if not msg or not self.my_name: return
        cmd = "EDIT_MSG" if msg_id_to_edit else "CHAT_MSG"
        msg_id = msg_id_to_edit if msg_id_to_edit else str(uuid.uuid4())
        full_command = f"{cmd}:{msg_id}:{self.my_name}:{msg}"
        self.send_command(full_command); self.process_command(full_command)
        self.chat_entry.delete(0, tk.END)
        if msg_id_to_edit: self.send_button.configure(text="Send", command=self.send_chat_message)

    def edit_chat_prompt(self, msg_id):
        frame = self.chat_messages[msg_id].winfo_children()[0]
        if len(frame.winfo_children()) > 1 and isinstance(frame.winfo_children()[1], ctk.CTkLabel):
            original_text = frame.winfo_children()[1].cget("text")
            self.chat_entry.delete(0, tk.END); self.chat_entry.insert(0, original_text)
            self.send_button.configure(text="Save", command=lambda: self.send_chat_message(msg_id_to_edit=msg_id))
        else:
            messagebox.showinfo("Cannot Edit", "This message type cannot be edited.")

    def confirm_clear_chat(self):
        if messagebox.askyesno("Confirm", "Are you sure you want to clear the chat history for everyone?"): 
            self.send_command("CLEAR_CHAT")
            # The actual clearing happens in process_command.
            # We don't need to call process_command("CLEAR_CHAT") directly here,
            # as it will be received back from our own send_command.
            self.update_status("Chat clear requested!", "white") 

    # NEW HELPER METHOD TO CREATE THE VISUAL WIDGET FOR A GALLERY ITEM
    def _create_gallery_item_widget(self, file_id, filename, local_path):
        """Creates and stores the CTkFrame widget for a file gallery item."""
        print(f"DEBUG: _create_gallery_item_widget called for ID: {file_id}, Filename: {filename}")

        # If widget already exists (e.g., re-drawing), destroy it before recreating
        if file_id in self.file_gallery_widgets:
            self.file_gallery_widgets[file_id].destroy()
            del self.file_gallery_widgets[file_id]

        file_frame = ctk.CTkFrame(self.gallery_frame, width=150, height=150, corner_radius=10, fg_color="gray15")
        file_frame.grid_propagate(False)

        img_label = None
        try:
            img = Image.open(local_path)
            img.thumbnail((96, 96))
            thumb_img = ImageTk.PhotoImage(img)
            img_label = ctk.CTkLabel(file_frame, image=thumb_img, text="")
            img_label.image = thumb_img # Keep a reference!
            img_label.pack(pady=(10, 5))
        except Exception as e:
            print(f"WARNING: Could not generate thumbnail for {filename}: {e}. Using default icon.")
            img_label = ctk.CTkLabel(file_frame, text="📄", font=("Arial", 48), width=96, height=96,
                                     fg_color="gray25", corner_radius=6)
            img_label.pack(pady=(10, 5))

        ctk.CTkLabel(file_frame, text=filename, wraplength=120, justify="center",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(0, 0))

        file_type = os.path.splitext(filename)[1].upper()[1:] or "FILE"
        if not file_type:
            file_type = "FILE"
        ctk.CTkLabel(file_frame, text=file_type, font=("Arial", 11, "italic"), text_color="gray").pack(pady=(0, 5))

        button_frame = ctk.CTkFrame(file_frame, fg_color="transparent")
        button_frame.pack(pady=(0, 10), padx=10)

        ctk.CTkButton(button_frame, text="Download", width=70, height=25, font=ctk.CTkFont(size=14),
                      command=lambda id=file_id, name=filename: self.request_file_download(id, name)).pack(side="left", padx=(0, 2))

        ctk.CTkButton(button_frame, text="Delete", width=70, height=25, fg_color="#D32F2F", hover_color="#B71C1C", font=ctk.CTkFont(size=14),
                      command=lambda id=file_id, path=local_path: self.confirm_delete_file(id, path)).pack(side="right", padx=(2, 0))

        self.file_gallery_widgets[file_id] = file_frame
        print(f"DEBUG: Widget created for {filename}.")

    def add_file_to_gallery(self, file_id, filename, local_path):
        print(f"DEBUG: add_file_to_gallery called for ID: {file_id}, Filename: {filename}, Path: {local_path}")
        if not os.path.exists(local_path):
            print(f"ERROR: File not found at {local_path}, skipping gallery addition.")
            return

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
        self._rearrange_gallery_grid() # Recalculate and place all widgets to ensure correct grid layout
        self.gallery_frame.update_idletasks()
        print(f"DEBUG: File {filename} added to gallery. Total widgets: {len(self.file_gallery_widgets)}")

    def _rearrange_gallery_grid(self):
        """Rearranges all file widgets in the gallery frame into a grid."""
        print("DEBUG: _rearrange_gallery_grid called.")
        # Clear existing grid layout for all widgets in gallery_frame
        for widget in self.gallery_frame.winfo_children():
            # Ensure we only forget file frames, not the drag_drop_label
            if isinstance(widget, ctk.CTkFrame) and widget != self.drag_drop_label: 
                widget.grid_forget()

        row, col = 0, 0
        for file_id in self.file_gallery_items_metadata:
            if file_id in self.file_gallery_widgets: # Only try to grid if widget exists
                file_frame = self.file_gallery_widgets[file_id]
                file_frame.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")
                col += 1
                if col >= 4:  # 4 columns per row
                    col = 0
                    row += 1
        print(f"DEBUG: Rearranged {len(self.file_gallery_widgets)} widgets in gallery grid.")
        self.gallery_frame.update_idletasks()
        self._update_drag_drop_label_visibility()


    def send_file(self, filepath):
        if not filepath or not os.path.exists(filepath): 
            print(f"ERROR: Cannot send file. Path invalid or doesn't exist: {filepath}")
            return
        self.update_status(f"Requesting to send {os.path.basename(filepath)}...", "orange")
        filename, filesize = os.path.basename(filepath), os.path.getsize(filepath)
        file_id = str(uuid.uuid4())
        self.pending_transfers[file_id] = {"filepath": filepath, "filename": filename, "filesize": filesize} 
        
        # Add to gallery immediately locally
        self.add_file_to_gallery(file_id, filename, filepath) 
        
        self.send_command(f"FILE_REQUEST:{file_id}:{filename}:{filesize}")


    def _send_file_data(self, file_id):
        if file_id not in self.pending_transfers: return
        filepath = self.pending_transfers[file_id]['filepath']
        filename = self.pending_transfers[file_id]['filename'] 
        filesize = self.pending_transfers[file_id]['filesize'] 

        try:
            with open(filepath, 'rb') as f:
                self.send_command(f"FILE_START_TRANSFER:{file_id}:{filename}:{filesize}")
                if not self.connected.is_set():
                    raise ConnectionError("Connection lost during file send preparation.")
                while True:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    self.connection.sendall(chunk)
            self.update_status(f"Successfully sent {os.path.basename(filepath)}", "white")
            self.send_command(f"ADD_TO_GALLERY:{file_id}:{filename}") 
        except Exception as e: 
            print(f"Error sending file data: {e}"); 
            self.update_status(f"Failed to send file", "red")
            messagebox.showerror("File Transfer Error", f"Failed to send '{filename}': {e}")
        finally: 
            if file_id in self.pending_transfers:
                del self.pending_transfers[file_id]

    def request_file_download(self, file_id, filename):
        self.update_status(f"Requested download of '{filename}'", "white") # Changed to white
        self.send_command(f"REQUEST_DOWNLOAD:{file_id}")

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
                with open(self.config_file, 'r') as f: config = json.load(f)
                last_profile = config.get("last_profile")
                if last_profile and last_profile != "Select Profile":
                    self.profile_menu.set(last_profile); self.profile_selected(last_profile)
            
            if os.path.exists(self.chat_history_file):
                # Clear existing chat messages before loading from history
                for w in list(self.chat_messages.values()):
                    w.destroy()
                self.chat_messages.clear()
                with open(self.chat_history_file, 'r') as f:
                    for line in f: self.process_command(line.strip(), from_history=True)
                print(f"DEBUG: Loaded chat history from {self.chat_history_file}")

            # Load file gallery metadata and build widgets
            if os.path.exists(self.file_gallery_metadata_file):
                print(f"DEBUG: Loading file gallery metadata from {self.file_gallery_metadata_file}")
                with open(self.file_gallery_metadata_file, 'r') as f:
                    loaded_files_from_json = json.load(f)
                
                # 1. Clear existing widgets and metadata
                for widget_id in list(self.file_gallery_widgets.keys()):
                    if widget_id in self.file_gallery_widgets:
                        self.file_gallery_widgets[widget_id].destroy()
                self.file_gallery_widgets.clear()
                self.file_gallery_items_metadata.clear() 
                
                valid_files_count = 0
                temp_metadata_storage = {} # Use a temporary dict for clean loading

                # First, load all valid metadata into a temporary storage
                for file_data in loaded_files_from_json:
                    file_id = file_data.get("file_id")
                    filename = file_data.get("filename")
                    local_path = file_data.get("local_path")
                    if file_id and filename and local_path and os.path.exists(local_path):
                        temp_metadata_storage[file_id] = {
                            "file_id": file_id, "filename": filename, "local_path": local_path
                        }
                        valid_files_count += 1
                    else:
                        print(f"WARNING: Skipping invalid/missing file from history: {file_data}")
                
                # Now, update the main metadata dictionary
                self.file_gallery_items_metadata.update(temp_metadata_storage)

                # Then, create widgets for all currently loaded valid files
                for file_id, file_info in self.file_gallery_items_metadata.items():
                    self._create_gallery_item_widget(file_id, file_info["filename"], file_info["local_path"])

                # Finally, arrange the grid, save, and update visibility once
                self._rearrange_gallery_grid()
                self._save_file_gallery_metadata() # Re-save to clean up any invalid entries
                self._update_drag_drop_label_visibility() 
                print(f"DEBUG: Loaded {valid_files_count} files into gallery metadata and displayed.")

        except Exception as e: 
            print(f"ERROR: Error loading config or history: {e}")

    def on_closing(self):
        config = {"last_profile": self.profile_menu.get() if self.my_name else "Select Profile"}
        try:
            with open(self.config_file, 'w') as f: json.dump(config, f)
        except Exception as e:
            print(f"Error saving config: {e}")

        self._save_file_gallery_metadata()

        if self.connection: self.connection.close()
        self.master.destroy()

    def process_command(self, command_str, from_history=False):
        try:
            cmd_parts = command_str.split(":", 1)
            cmd = cmd_parts[0]
            data = cmd_parts[1] if len(cmd_parts) > 1 else ""

            print(f"DEBUG: Processing command: {command_str}")

            if cmd == "CHAT_MSG": 
                _, msg_id, sender, message = command_str.split(":", 3)
                self.add_chat_message(msg_id, sender, message, is_own=(sender == self.my_name))
            elif cmd == "EDIT_MSG": 
                _, msg_id, _, new_message = command_str.split(":", 3)
                if msg_id in self.chat_messages:
                    msg_frame = self.chat_messages[msg_id].winfo_children()[0]
                    if len(msg_frame.winfo_children()) > 1 and isinstance(msg_frame.winfo_children()[1], ctk.CTkLabel):
                        msg_frame.winfo_children()[1].configure(text=new_message)
            elif cmd == "DELETE_MSG": 
                _, msg_id = command_str.split(":", 1)
                if msg_id in self.chat_messages:
                    self.chat_messages[msg_id].destroy()
                    del self.chat_messages[msg_id]
            elif cmd == "CLEAR_CHAT": 
                print("DEBUG: Executing CLEAR_CHAT command.")
                for w in list(self.chat_messages.values()): # Iterate over a copy
                    w.destroy()
                self.chat_messages.clear()
                # Ensure the history file is also cleared
                with open(self.chat_history_file, 'w') as f: f.truncate(0) 
                self.update_status("Chat history cleared!", "white")
            elif cmd == "DRAW": 
                x1, y1, x2, y2, color, size = data.split(",")
                self.canvas.create_line(int(x1), int(y1), int(x2), int(y2), width=float(size), fill=color, capstyle=tk.ROUND, smooth=tk.TRUE)
            elif cmd == "CLEAR": 
                self.canvas.delete("all")
            elif cmd == "MOUSE_MOVE":
                x, y, name = data.split(",", 2)
                self.update_remote_mouse(int(x), int(y), name)
            elif cmd == "MOUSE_LEAVE":
                self.clear_remote_mouse()
            elif cmd == "FILE_REQUEST":
                _, file_id, filename, filesize = command_str.split(":", 3)
                self.pending_transfers[file_id] = {"filename": filename, "filesize": int(filesize)}
                self.send_command(f"FILE_ACCEPT:{file_id}") 
                self.update_status(f"Automatically accepting incoming file: '{filename}'", "white") 
            elif cmd == "FILE_ACCEPT": 
                _, file_id = command_str.split(":", 1)
                if file_id in self.pending_transfers: 
                    if "filepath" in self.pending_transfers[file_id]: 
                        threading.Thread(target=self._send_file_data, args=(file_id,), daemon=True).start()
                else:
                    print(f"Received FILE_ACCEPT for unknown file_id: {file_id}")
            elif cmd == "FILE_REJECT": 
                _, file_id = command_str.split(":", 1)
                if file_id in self.pending_transfers: 
                    del self.pending_transfers[file_id]
                self.update_status("File transfer rejected by peer.", "orange")
            elif cmd == "ADD_TO_GALLERY":
                _, file_id, filename = command_str.split(":", 2)
                local_path = os.path.join(self.downloads_folder, f"{file_id}_{filename}")
                self.after(10, self.add_file_to_gallery, file_id, filename, local_path)
            elif cmd == "REQUEST_DOWNLOAD":
                _, file_id = command_str.split(":", 1)
                if file_id in self.file_gallery_items_metadata:
                    filepath_to_send = self.file_gallery_items_metadata[file_id]['local_path']
                    self.pending_transfers[file_id] = {
                        "filepath": filepath_to_send,
                        "filename": os.path.basename(filepath_to_send),
                        "filesize": os.path.getsize(filepath_to_send)
                    }
                    threading.Thread(target=self._send_file_data, args=(file_id,), daemon=True).start()
                else:
                    print(f"ERROR: Peer requested download for unknown file_id: {file_id}")
            elif cmd == "DELETE_FILE_COMMAND": 
                _, file_id = command_str.split(":", 1)
                local_path_to_delete = self.file_gallery_items_metadata.get(file_id, {}).get('local_path')
                self.delete_file(file_id, local_path_to_delete, is_remote_command=True)

            if not from_history: self.notify_user()
            # Only log commands that should persist in history for both users, excluding CLEAR_CHAT
            if not from_history and cmd not in ["CLEAR_CHAT"] and cmd in ["CHAT_MSG", "EDIT_MSG", "DELETE_MSG", "ADD_TO_GALLERY", "DELETE_FILE_COMMAND"]:
                with open(self.chat_history_file, 'a') as f:
                     f.write(command_str + '\n')
        except Exception as e: print(f"ERROR: Error processing command: {e} -> '{command_str}'")

    def receive_data(self):
        buffer = b""; separator = b"\n"; receiving_file_info = None
        while self.connected.is_set():
            try:
                chunk = self.connection.recv(8192)
                if not chunk: self.handle_disconnect(); break
                
                if receiving_file_info:
                    buffer += chunk
                    filepath, filesize, file_id, original_filename = (
                        receiving_file_info['path'], 
                        receiving_file_info['size'], 
                        receiving_file_info['id'], 
                        receiving_file_info['original_filename']
                    )
                    
                    if len(buffer) >= filesize:
                        file_data, buffer = buffer[:filesize], buffer[filesize:]
                        with open(filepath, 'wb') as f: f.write(file_data)
                        self.update_status(f"Successfully received {original_filename}", "white") 
                        self.after(10, self.add_file_to_gallery, file_id, original_filename, filepath)
                        receiving_file_info = None
                    continue
                
                buffer += chunk
                while separator in buffer:
                    line_bytes, buffer = buffer.split(separator, 1)
                    command_str = line_bytes.decode('utf-8', errors='ignore')

                    if command_str.startswith("FILE_START_TRANSFER"):
                        _, file_id, filename_from_cmd, filesize_str = command_str.split(":", 3)

                        save_filename = filename_from_cmd
                        if file_id in self.pending_transfers and 'filename' in self.pending_transfers[file_id]:
                            save_filename = self.pending_transfers[file_id]['filename']

                        save_path = os.path.join(self.downloads_folder, f"{file_id}_{save_filename}")

                        receiving_file_info = {"id": file_id, "path": save_path, "size": int(filesize_str), "original_filename": save_filename}

                        if len(buffer) >= int(filesize_str):
                            file_data, buffer = buffer[:int(filesize_str)], buffer[int(filesize_str):]
                            with open(save_path, 'wb') as f: f.write(file_data)
                            self.update_status(f"Successfully received {save_filename}", "white") 
                            self.after(10, self.add_file_to_gallery, file_id, save_filename, save_path)
                            receiving_file_info = None
                        continue
                    self.process_command(command_str)
            except Exception as e:
                print(f"Error receiving data: {e}")
                self.handle_disconnect()
                break

    def send_command(self, command):
        if self.connected.is_set() and self.connection:
            try:
                self.connection.sendall((command + "\n").encode('utf-8'))
            except Exception as e:
                print(f"Error sending command: {e}")
                self.handle_disconnect()

    def start_server(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.server_socket.bind((self.host_ip_listen, self.port))
            self.server_socket.listen(1)
            self.update_status(f"Listening for connections on {self.host_ip_listen}:{self.port}", "white")
            threading.Thread(target=self._accept_connections, daemon=True).start()
        except Exception as e:
            self.update_status(f"Failed to start server: {e}", "red")
            messagebox.showerror("Server Error", f"Failed to start server: {e}\nPlease ensure the port is not in use.")

    def _accept_connections(self):
        while True:
            try:
                conn, addr = self.server_socket.accept()
                if self.connected.is_set():
                    conn.close()
                    continue
                self.connection = conn
                self.connected.set()
                self.update_status(f"Connected to {addr[0]}", "green")
                threading.Thread(target=self.receive_data, daemon=True).start()
            except Exception as e:
                if self.connected.is_set(): # Only print if not intentionally closed
                    print(f"Error accepting connections: {e}")
                break

    def connect_to_peer(self):
        peer_ip = self.ip_entry.get()
        if not peer_ip:
            self.update_status("Please enter a peer IP.", "orange")
            return
        if self.connected.is_set():
            self.update_status("Already connected!", "orange")
            return

        self.update_status(f"Attempting to connect to {peer_ip}:{self.port}...", "orange")
        threading.Thread(target=self._initiate_connection, args=(peer_ip,), daemon=True).start()

    def _initiate_connection(self, peer_ip):
        try:
            temp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            temp_socket.connect((peer_ip, self.port))
            self.connection = temp_socket
            self.connected.set()
            self.update_status(f"Connected to {peer_ip}", "green")
            threading.Thread(target=self.receive_data, daemon=True).start()
        except Exception as e:
            self.update_status(f"Failed to connect to {peer_ip}: {e}", "red")
            self.connection = None
            self.connected.clear()

    def handle_disconnect(self):
        if self.connected.is_set():
            self.connected.clear()
            if self.connection:
                try:
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                except OSError as e:
                    print(f"Error during socket shutdown/close: {e}")
                finally:
                    self.connection = None
            self.update_status("Disconnected.", "red")
            self.clear_remote_mouse()
            self.peer_name = None

    def update_status(self, message, color="white"):
        self.after(0, lambda: self.status_label.configure(text=f"Status: {message}", text_color=color))

    def profile_selected(self, choice):
        if choice == f"I am {self.NATHAN_NAME}":
            self.my_name = self.NATHAN_NAME
            self.ip_entry.delete(0, tk.END)
            self.ip_entry.insert(0, self.MAJID_IP)
        elif choice == f"I am {self.MAJID_NAME}":
            self.my_name = self.MAJID_NAME
            self.ip_entry.delete(0, tk.END)
            self.ip_entry.insert(0, self.NATHAN_IP)
        else:
            self.my_name = None
            self.ip_entry.delete(0, tk.END)
        self.update_status(f"Profile set to: {self.my_name}", "cyan")
        print(f"Profile selected: {self.my_name}")
        self.profile_menu.set(choice)

    def draw(self, event):
        if self.old_x and self.old_y:
            self.canvas.create_line(self.old_x, self.old_y, event.x, event.y,
                                    width=self.brush_size, fill=self.color,
                                    capstyle=tk.ROUND, smooth=tk.TRUE)
            self.send_command(f"DRAW:{self.old_x},{self.old_y},{event.x},{event.y},{self.color},{self.brush_size}")
        self.old_x, self.old_y = event.x, event.y

    def reset_drawing_state(self, event): self.old_x, self.old_y = None, None
    def clear_canvas(self): self.canvas.delete("all"); self.send_command("CLEAR")

    def update_remote_mouse(self, x, y, name):
        if not self.remote_mouse:
            self.remote_mouse = self.canvas.create_oval(x-5, y-5, x+5, y+5, fill="red", outline="white")
            self.remote_mouse_label_id = self.canvas.create_text(x+10, y-10, anchor="nw", text=name, fill="red", font=("Arial", 10, "bold"))
        else:
            self.canvas.coords(self.remote_mouse, x-5, y-5, x+5, y+5)
            self.canvas.coords(self.remote_mouse_label_id, x+10, y-10)
            self.canvas.itemconfig(self.remote_mouse_label_id, text=name)
        self.last_mouse_move_time = time.time()

    def clear_remote_mouse(self):
        if self.remote_mouse:
            self.canvas.delete(self.remote_mouse)
            self.remote_mouse = None
        if self.remote_mouse_label_id:
            self.canvas.delete(self.remote_mouse_label_id)
            self.remote_mouse_label_id = None
        self.last_mouse_move_time = 0

    def check_remote_mouse_timeout(self):
        if self.remote_mouse and (time.time() - self.last_mouse_move_time > 5):
            self.clear_remote_mouse()
        self.canvas.after(1000, self.check_remote_mouse_timeout)

    def send_mouse_position(self, event):
        if self.my_name and self.connected.is_set():
            self.send_command(f"MOUSE_MOVE:{event.x},{event.y},{self.my_name}")

    def send_mouse_leave(self, event):
        if self.my_name and self.connected.is_set():
            self.send_command("MOUSE_LEAVE")

    def confirm_delete_file(self, file_id, local_path):
        filename = self.file_gallery_items_metadata.get(file_id, {}).get("filename", "this file")
        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete '{filename}'? This will also remove it from the shared gallery for everyone."):
            self.delete_file(file_id, local_path, is_remote_command=False)
            self.send_command(f"DELETE_FILE_COMMAND:{file_id}")

    def delete_file(self, file_id, local_path, is_remote_command):
        print(f"DEBUG: Deleting file ID: {file_id}, Path: {local_path}, Remote command: {is_remote_command}")
        if file_id in self.file_gallery_items_metadata:
            del self.file_gallery_items_metadata[file_id]

        if file_id in self.file_gallery_widgets:
            self.file_gallery_widgets[file_id].destroy()
            del self.file_gallery_widgets[file_id]

        if local_path and os.path.exists(local_path):
            try:
                os.remove(local_path)
                print(f"DEBUG: Successfully deleted local file: {local_path}")
            except Exception as e:
                print(f"ERROR: Could not delete local file {local_path}: {e}")
                if not is_remote_command:
                    messagebox.showerror("File Deletion Error", f"Could not delete local file: {e}")

        self._save_file_gallery_metadata()
        self._rearrange_gallery_grid() # Re-layout the remaining files
        self._update_drag_drop_label_visibility()
        if not is_remote_command:
            self.update_status(f"File deleted and removed from gallery.", "white")

    def notify_user(self):
        if self.master.attributes("-topmost"): return
        self.master.attributes('-alpha', 0.8)
        self.master.after(200, lambda: self.master.attributes('-alpha', 1.0))

if __name__ == "__main__":
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")

    root = TkinterDnD.Tk()
    root.title("Vortex Tunnel")
    root.geometry("800x600")

    # Use the resource_path helper for the icon
    icon_path = resource_path('vortex.ico')

    # Debugging print statements (useful for checking during development/build)
    print(f"Attempting to load icon from: {icon_path}")
    print(f"Does icon file exist? {os.path.exists(icon_path)}")

    try:
        root.iconbitmap(default=icon_path)
    except Exception as e: # Catch a broader exception for initial testing
        print(f"Error loading icon: {e}")
        print("Make sure 'vortex.ico' is a valid .ico file and is accessible.")


    root.grid_columnconfigure(0, weight=1)
    root.grid_rowconfigure(0, weight=1)

    app = VortexTunnelApp(master=root)
    app.grid(row=0, column=0, sticky="nsew")

    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()