"""
Simple GUI to monitor Instagram posting progress.
Shows real-time output from post_reel_smart.py
"""
import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import subprocess
import threading
import queue
import csv


class PostingMonitor:
    def __init__(self, root):
        self.root = root
        self.root.title("Instagram Posting Monitor")
        self.root.geometry("900x700")

        self.process = None
        self.output_queue = queue.Queue()

        self.setup_ui()
        self.load_csv_data()

    def setup_ui(self):
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Top section - Configuration
        config_frame = ttk.LabelFrame(main_frame, text="Configuration", padding="10")
        config_frame.pack(fill=tk.X, pady=(0, 10))

        # Phone selection
        ttk.Label(config_frame, text="Phone:").grid(row=0, column=0, sticky=tk.W, padx=5)
        self.phone_var = tk.StringVar(value="miccliparchive")
        phone_combo = ttk.Combobox(config_frame, textvariable=self.phone_var, width=20)
        phone_combo['values'] = ('miccliparchive', 'reelwisdompod_', 'podmindstudio', 'talktrackhub')
        phone_combo.grid(row=0, column=1, sticky=tk.W, padx=5)

        # Video selection
        ttk.Label(config_frame, text="Video:").grid(row=0, column=2, sticky=tk.W, padx=5)
        self.video_var = tk.StringVar()
        self.video_combo = ttk.Combobox(config_frame, textvariable=self.video_var, width=50)
        self.video_combo.grid(row=0, column=3, sticky=tk.W, padx=5)
        self.video_combo.bind('<<ComboboxSelected>>', self.on_video_selected)

        # Caption display
        caption_frame = ttk.LabelFrame(main_frame, text="Caption", padding="10")
        caption_frame.pack(fill=tk.X, pady=(0, 10))

        self.caption_text = scrolledtext.ScrolledText(caption_frame, height=4, wrap=tk.WORD)
        self.caption_text.pack(fill=tk.X)

        # Status section
        status_frame = ttk.LabelFrame(main_frame, text="Status", padding="10")
        status_frame.pack(fill=tk.X, pady=(0, 10))

        self.status_var = tk.StringVar(value="Ready")
        self.status_label = ttk.Label(status_frame, textvariable=self.status_var, font=('Arial', 12, 'bold'))
        self.status_label.pack(side=tk.LEFT)

        self.progress = ttk.Progressbar(status_frame, mode='indeterminate', length=200)
        self.progress.pack(side=tk.RIGHT, padx=10)

        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(0, 10))

        self.start_btn = ttk.Button(button_frame, text="Start Posting", command=self.start_posting)
        self.start_btn.pack(side=tk.LEFT, padx=5)

        self.stop_btn = ttk.Button(button_frame, text="Stop", command=self.stop_posting, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        ttk.Button(button_frame, text="Clear Log", command=self.clear_log).pack(side=tk.LEFT, padx=5)

        ttk.Button(button_frame, text="Reload CSV", command=self.load_csv_data).pack(side=tk.RIGHT, padx=5)

        # Log output
        log_frame = ttk.LabelFrame(main_frame, text="Log Output", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=20, wrap=tk.WORD,
                                                   font=('Consolas', 10))
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Configure tags for colored output
        self.log_text.tag_config('info', foreground='black')
        self.log_text.tag_config('success', foreground='green')
        self.log_text.tag_config('error', foreground='red')
        self.log_text.tag_config('step', foreground='blue')
        self.log_text.tag_config('action', foreground='purple')

    def load_csv_data(self):
        """Load video/caption data from CSV"""
        csv_path = r'C:\Users\asus\Desktop\projects\geelark-automation\chunk_01a\chunk_01a.csv'
        self.posts = []

        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    original_path = row.get('Shortcode', '').strip()
                    if not original_path:
                        continue

                    # Replace spoofed with chunk_01a
                    video_path = original_path.replace('spoofed', 'chunk_01a')

                    if os.path.exists(video_path):
                        caption = row.get('Text', '').strip()
                        # Extract short name from path
                        short_name = os.path.basename(video_path)
                        folder = os.path.basename(os.path.dirname(video_path))
                        display_name = f"{folder}/{short_name}"

                        self.posts.append({
                            'display': display_name,
                            'path': video_path,
                            'caption': caption
                        })

            # Update combobox
            self.video_combo['values'] = [p['display'] for p in self.posts]
            if self.posts:
                self.video_combo.current(0)
                self.on_video_selected(None)

            self.log(f"Loaded {len(self.posts)} videos from CSV", 'success')

        except Exception as e:
            self.log(f"Error loading CSV: {e}", 'error')

    def on_video_selected(self, event):
        """Update caption when video is selected"""
        idx = self.video_combo.current()
        if 0 <= idx < len(self.posts):
            self.caption_text.delete('1.0', tk.END)
            self.caption_text.insert('1.0', self.posts[idx]['caption'])

    def log(self, message, tag='info'):
        """Add message to log"""
        self.log_text.insert(tk.END, message + '\n', tag)
        self.log_text.see(tk.END)

    def clear_log(self):
        """Clear the log"""
        self.log_text.delete('1.0', tk.END)

    def start_posting(self):
        """Start the posting process"""
        idx = self.video_combo.current()
        if idx < 0 or idx >= len(self.posts):
            messagebox.showerror("Error", "Please select a video")
            return

        post = self.posts[idx]
        phone = self.phone_var.get()

        self.log(f"\n{'='*50}", 'info')
        self.log(f"Starting post to {phone}", 'step')
        self.log(f"Video: {post['path']}", 'info')
        self.log(f"Caption: {post['caption'][:100]}...", 'info')
        self.log(f"{'='*50}\n", 'info')

        # Disable start, enable stop
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.progress.start()
        self.status_var.set("Connecting...")

        # Run in background thread
        self.running = True
        thread = threading.Thread(target=self.run_posting, args=(phone, post['path'], post['caption']))
        thread.daemon = True
        thread.start()

        # Start checking output
        self.check_output()

    def run_posting(self, phone, video_path, caption):
        """Run the posting script in a subprocess"""
        try:
            script_path = os.path.join(os.path.dirname(__file__), 'post_reel_smart.py')

            self.process = subprocess.Popen(
                [sys.executable, '-u', script_path, phone, video_path, caption],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1,
                cwd=os.path.dirname(__file__)
            )

            # Read output line by line
            for line in iter(self.process.stdout.readline, ''):
                if not self.running:
                    break
                self.output_queue.put(line.rstrip())

            self.process.wait()
            exit_code = self.process.returncode

            if exit_code == 0:
                self.output_queue.put(('SUCCESS', 'Post completed successfully!'))
            else:
                self.output_queue.put(('FAILED', f'Post failed with exit code {exit_code}'))

        except Exception as e:
            self.output_queue.put(('ERROR', str(e)))
        finally:
            self.output_queue.put(('DONE', None))

    def check_output(self):
        """Check for new output from the subprocess"""
        try:
            while True:
                item = self.output_queue.get_nowait()

                if isinstance(item, tuple):
                    msg_type, msg = item
                    if msg_type == 'DONE':
                        self.posting_finished()
                        return
                    elif msg_type == 'SUCCESS':
                        self.log(f"\n{msg}", 'success')
                        self.status_var.set("SUCCESS!")
                    elif msg_type == 'FAILED':
                        self.log(f"\n{msg}", 'error')
                        self.status_var.set("FAILED")
                    elif msg_type == 'ERROR':
                        self.log(f"\nERROR: {msg}", 'error')
                        self.status_var.set("ERROR")
                else:
                    # Regular log line
                    line = item

                    # Color code based on content
                    if '--- Step' in line:
                        self.log(line, 'step')
                        # Update status with step number
                        self.status_var.set(line.strip('- '))
                    elif '[TAP]' in line or 'Action:' in line:
                        self.log(line, 'action')
                    elif '[SUCCESS]' in line or '[OK]' in line:
                        self.log(line, 'success')
                    elif '[ERROR]' in line or '[FAIL]' in line or 'ERROR' in line:
                        self.log(line, 'error')
                    elif 'Uploading' in line or 'Connecting' in line or 'Opening' in line:
                        self.log(line, 'step')
                        self.status_var.set(line.strip())
                    else:
                        self.log(line, 'info')

        except queue.Empty:
            pass

        # Schedule next check
        if self.running:
            self.root.after(100, self.check_output)

    def posting_finished(self):
        """Called when posting is complete"""
        self.running = False
        self.process = None
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.progress.stop()

    def stop_posting(self):
        """Stop the posting process"""
        self.running = False
        if self.process:
            self.process.terminate()
            self.log("\nPosting stopped by user", 'error')
            self.status_var.set("Stopped")
        self.posting_finished()


def main():
    root = tk.Tk()
    app = PostingMonitor(root)
    root.mainloop()


if __name__ == "__main__":
    main()
