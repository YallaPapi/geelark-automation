"""
Posting Dashboard - Full GUI for Instagram posting automation.

Features:
- Add multiple video folders
- Manage accounts
- Configure retry/humanize/delay settings
- Start/Stop/Pause scheduler
- Real-time status and progress
- Job queue view
"""
import sys
import os

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import threading
from datetime import datetime

from posting_scheduler import PostingScheduler, PostStatus


class PostingDashboard:
    def __init__(self, root):
        self.root = root
        self.root.title("Instagram Posting Dashboard")
        self.root.geometry("1100x800")

        # Initialize scheduler
        self.scheduler = PostingScheduler()
        self.scheduler.on_status_update = self.log
        self.scheduler.on_job_complete = self.on_job_complete

        self.setup_ui()
        self.refresh_all()

        # Auto-refresh stats every 2 seconds
        self.auto_refresh()

    def setup_ui(self):
        # Main container with left and right panels
        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Left panel - Configuration
        left_frame = ttk.Frame(main_paned, width=400)
        main_paned.add(left_frame, weight=1)

        # Right panel - Status and logs
        right_frame = ttk.Frame(main_paned, width=600)
        main_paned.add(right_frame, weight=2)

        # === LEFT PANEL ===

        # Video Folders Section
        folders_frame = ttk.LabelFrame(left_frame, text="Video Folders", padding=10)
        folders_frame.pack(fill=tk.X, pady=(0, 10))

        self.folders_listbox = tk.Listbox(folders_frame, height=4)
        self.folders_listbox.pack(fill=tk.X, pady=(0, 5))

        folders_btn_frame = ttk.Frame(folders_frame)
        folders_btn_frame.pack(fill=tk.X)
        ttk.Button(folders_btn_frame, text="Add Folder", command=self.add_folder).pack(side=tk.LEFT, padx=2)
        ttk.Button(folders_btn_frame, text="Remove", command=self.remove_folder).pack(side=tk.LEFT, padx=2)
        ttk.Button(folders_btn_frame, text="Reload", command=self.reload_folders).pack(side=tk.LEFT, padx=2)

        # Accounts Section
        accounts_frame = ttk.LabelFrame(left_frame, text="Accounts", padding=10)
        accounts_frame.pack(fill=tk.X, pady=(0, 10))

        self.accounts_listbox = tk.Listbox(accounts_frame, height=6, selectmode=tk.EXTENDED)
        self.accounts_listbox.pack(fill=tk.X, pady=(0, 5))

        accounts_btn_frame = ttk.Frame(accounts_frame)
        accounts_btn_frame.pack(fill=tk.X)
        ttk.Button(accounts_btn_frame, text="Add", command=self.add_account).pack(side=tk.LEFT, padx=2)
        ttk.Button(accounts_btn_frame, text="Remove", command=self.remove_account).pack(side=tk.LEFT, padx=2)

        # Add account entry
        self.account_entry = ttk.Entry(accounts_frame)
        self.account_entry.pack(fill=tk.X, pady=(5, 0))
        self.account_entry.bind('<Return>', lambda e: self.add_account())

        # Settings Section
        settings_frame = ttk.LabelFrame(left_frame, text="Settings", padding=10)
        settings_frame.pack(fill=tk.X, pady=(0, 10))

        # Humanize
        self.humanize_var = tk.BooleanVar(value=self.scheduler.humanize)
        ttk.Checkbutton(settings_frame, text="Humanize (random actions)",
                       variable=self.humanize_var, command=self.save_settings).pack(anchor=tk.W)

        # Test retry mode
        self.test_retry_var = tk.BooleanVar(value=self.scheduler.test_retry_mode)
        ttk.Checkbutton(settings_frame, text="TEST MODE: Force 1st attempt to fail",
                       variable=self.test_retry_var, command=self.save_settings).pack(anchor=tk.W)

        # Max retries
        retry_frame = ttk.Frame(settings_frame)
        retry_frame.pack(fill=tk.X, pady=5)
        ttk.Label(retry_frame, text="Max retries:").pack(side=tk.LEFT)
        self.retries_var = tk.StringVar(value=str(self.scheduler.max_retries))
        retry_spin = ttk.Spinbox(retry_frame, from_=1, to=10, width=5,
                                  textvariable=self.retries_var, command=self.save_settings)
        retry_spin.pack(side=tk.LEFT, padx=5)

        # Retry delay (in seconds for UI, stored as minutes internally)
        delay_frame = ttk.Frame(settings_frame)
        delay_frame.pack(fill=tk.X, pady=5)
        ttk.Label(delay_frame, text="Retry delay (sec):").pack(side=tk.LEFT)
        retry_secs = int(self.scheduler.retry_delay_minutes * 60)
        self.retry_delay_var = tk.StringVar(value=str(retry_secs))
        delay_spin = ttk.Spinbox(delay_frame, from_=5, to=300, width=5,
                                  textvariable=self.retry_delay_var, command=self.save_settings)
        delay_spin.pack(side=tk.LEFT, padx=5)

        # Post delay
        post_delay_frame = ttk.Frame(settings_frame)
        post_delay_frame.pack(fill=tk.X, pady=5)
        ttk.Label(post_delay_frame, text="Delay between posts (s):").pack(side=tk.LEFT)
        self.post_delay_var = tk.StringVar(value=str(self.scheduler.delay_between_posts))
        post_delay_spin = ttk.Spinbox(post_delay_frame, from_=10, to=300, width=5,
                                       textvariable=self.post_delay_var, command=self.save_settings)
        post_delay_spin.pack(side=tk.LEFT, padx=5)

        # Posts per day
        ppd_frame = ttk.Frame(settings_frame)
        ppd_frame.pack(fill=tk.X, pady=5)
        ttk.Label(ppd_frame, text="Posts per account/day:").pack(side=tk.LEFT)
        self.ppd_var = tk.StringVar(value=str(self.scheduler.posts_per_account_per_day))
        ppd_spin = ttk.Spinbox(ppd_frame, from_=1, to=10, width=5,
                                textvariable=self.ppd_var, command=self.save_settings)
        ppd_spin.pack(side=tk.LEFT, padx=5)

        # Control Buttons
        control_frame = ttk.LabelFrame(left_frame, text="Control", padding=10)
        control_frame.pack(fill=tk.X, pady=(0, 10))

        btn_row1 = ttk.Frame(control_frame)
        btn_row1.pack(fill=tk.X, pady=2)

        self.start_btn = ttk.Button(btn_row1, text="START", command=self.start_scheduler)
        self.start_btn.pack(side=tk.LEFT, padx=2, expand=True, fill=tk.X)

        self.pause_btn = ttk.Button(btn_row1, text="PAUSE", command=self.pause_scheduler, state=tk.DISABLED)
        self.pause_btn.pack(side=tk.LEFT, padx=2, expand=True, fill=tk.X)

        self.stop_btn = ttk.Button(btn_row1, text="STOP", command=self.stop_scheduler, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=2, expand=True, fill=tk.X)

        btn_row2 = ttk.Frame(control_frame)
        btn_row2.pack(fill=tk.X, pady=2)

        ttk.Button(btn_row2, text="Retry All Failed", command=self.retry_all_failed).pack(side=tk.LEFT, padx=2, expand=True, fill=tk.X)
        ttk.Button(btn_row2, text="View Report", command=self.show_error_report).pack(side=tk.LEFT, padx=2, expand=True, fill=tk.X)
        ttk.Button(btn_row2, text="Clear Log", command=self.clear_log).pack(side=tk.LEFT, padx=2, expand=True, fill=tk.X)

        # === RIGHT PANEL ===

        # Stats Section
        stats_frame = ttk.LabelFrame(right_frame, text="Status", padding=10)
        stats_frame.pack(fill=tk.X, pady=(0, 10))

        # Status indicator
        status_row = ttk.Frame(stats_frame)
        status_row.pack(fill=tk.X, pady=5)

        self.status_indicator = tk.Label(status_row, text="STOPPED", bg="gray", fg="white",
                                         font=('Arial', 12, 'bold'), width=15)
        self.status_indicator.pack(side=tk.LEFT, padx=5)

        # Stats labels
        stats_grid = ttk.Frame(stats_frame)
        stats_grid.pack(fill=tk.X)

        self.stats_labels = {}
        stats = [
            ('total', 'Total Jobs'),
            ('pending', 'Pending'),
            ('success', 'Success'),
            ('retrying', 'Retrying'),
            ('failed', 'Failed'),
        ]

        for i, (key, label) in enumerate(stats):
            ttk.Label(stats_grid, text=f"{label}:").grid(row=0, column=i*2, padx=5, sticky=tk.E)
            self.stats_labels[key] = ttk.Label(stats_grid, text="0", font=('Arial', 11, 'bold'))
            self.stats_labels[key].grid(row=0, column=i*2+1, padx=(0, 15), sticky=tk.W)

        # Progress bar
        self.progress = ttk.Progressbar(stats_frame, mode='determinate', length=400)
        self.progress.pack(fill=tk.X, pady=10)

        # Job Queue Section
        queue_frame = ttk.LabelFrame(right_frame, text="Job Queue", padding=10)
        queue_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Treeview for jobs
        columns = ('id', 'account', 'status', 'attempts', 'error')
        self.jobs_tree = ttk.Treeview(queue_frame, columns=columns, show='headings', height=10)

        self.jobs_tree.heading('id', text='Video ID')
        self.jobs_tree.heading('account', text='Account')
        self.jobs_tree.heading('status', text='Status')
        self.jobs_tree.heading('attempts', text='Attempts')
        self.jobs_tree.heading('error', text='Last Error')

        self.jobs_tree.column('id', width=150)
        self.jobs_tree.column('account', width=120)
        self.jobs_tree.column('status', width=80)
        self.jobs_tree.column('attempts', width=60)
        self.jobs_tree.column('error', width=200)

        scrollbar = ttk.Scrollbar(queue_frame, orient=tk.VERTICAL, command=self.jobs_tree.yview)
        self.jobs_tree.configure(yscrollcommand=scrollbar.set)

        self.jobs_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Context menu for jobs
        self.jobs_menu = tk.Menu(self.root, tearoff=0)
        self.jobs_menu.add_command(label="Retry Selected", command=self.retry_selected_job)
        self.jobs_tree.bind('<Button-3>', self.show_jobs_menu)

        # Log Section
        log_frame = ttk.LabelFrame(right_frame, text="Log", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=12, wrap=tk.WORD,
                                                   font=('Consolas', 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Configure log tags
        self.log_text.tag_config('info', foreground='black')
        self.log_text.tag_config('success', foreground='green')
        self.log_text.tag_config('error', foreground='red')
        self.log_text.tag_config('warning', foreground='orange')

    def log(self, message: str, tag: str = 'info'):
        """Add message to log"""
        # Detect tag from message content
        if '[OK]' in message or 'success' in message.lower():
            tag = 'success'
        elif '[FAIL]' in message or '[ERROR]' in message or 'error' in message.lower():
            tag = 'error'
        elif '[RETRY]' in message or 'retry' in message.lower():
            tag = 'warning'

        self.log_text.insert(tk.END, message + '\n', tag)
        self.log_text.see(tk.END)

    def clear_log(self):
        self.log_text.delete('1.0', tk.END)

    def add_folder(self):
        folder = filedialog.askdirectory(title="Select Video Folder")
        if folder:
            count = self.scheduler.add_video_folder(folder)
            self.refresh_folders()
            self.refresh_jobs()
            if count > 0:
                messagebox.showinfo("Success", f"Added {count} videos from folder")

    def remove_folder(self):
        selection = self.folders_listbox.curselection()
        if selection:
            folder = self.folders_listbox.get(selection[0])
            if folder in self.scheduler.video_folders:
                self.scheduler.video_folders.remove(folder)
                self.scheduler.save_state()
                self.refresh_folders()

    def reload_folders(self):
        """Reload all folders to pick up new videos"""
        for folder in self.scheduler.video_folders[:]:
            self.scheduler.add_video_folder(folder)
        self.refresh_jobs()
        self.log("Reloaded all folders")

    def add_account(self):
        name = self.account_entry.get().strip()
        if name:
            self.scheduler.add_account(name)
            self.account_entry.delete(0, tk.END)
            self.refresh_accounts()

    def remove_account(self):
        selection = self.accounts_listbox.curselection()
        for idx in reversed(selection):
            name = self.accounts_listbox.get(idx)
            self.scheduler.remove_account(name)
        self.refresh_accounts()

    def save_settings(self):
        """Save settings from UI to scheduler"""
        try:
            self.scheduler.humanize = self.humanize_var.get()
            self.scheduler.test_retry_mode = self.test_retry_var.get()
            self.scheduler.max_retries = int(self.retries_var.get())
            self.scheduler.retry_delay_minutes = float(self.retry_delay_var.get()) / 60  # Convert seconds to minutes
            self.scheduler.delay_between_posts = int(self.post_delay_var.get())
            self.scheduler.posts_per_account_per_day = int(self.ppd_var.get())
            self.scheduler.save_state()
        except ValueError:
            pass

    def start_scheduler(self):
        if not self.scheduler.accounts:
            messagebox.showerror("Error", "Add at least one account first")
            return
        if not self.scheduler.jobs:
            messagebox.showerror("Error", "Add a video folder first")
            return

        self.scheduler.start()
        self.start_btn.config(state=tk.DISABLED)
        self.pause_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.NORMAL)
        self.update_status_indicator()

    def pause_scheduler(self):
        if self.scheduler.paused:
            self.scheduler.resume()
            self.pause_btn.config(text="PAUSE")
        else:
            self.scheduler.pause()
            self.pause_btn.config(text="RESUME")
        self.update_status_indicator()

    def stop_scheduler(self):
        self.scheduler.stop()
        self.start_btn.config(state=tk.NORMAL)
        self.pause_btn.config(state=tk.DISABLED, text="PAUSE")
        self.stop_btn.config(state=tk.DISABLED)
        self.update_status_indicator()

    def retry_all_failed(self):
        self.scheduler.retry_all_failed()
        self.refresh_jobs()

    def show_error_report(self):
        """Show error report in a popup window"""
        report = self.scheduler.generate_error_report()

        # Create popup window
        popup = tk.Toplevel(self.root)
        popup.title("Error Report")
        popup.geometry("700x500")

        # Report text area
        report_text = scrolledtext.ScrolledText(popup, wrap=tk.WORD, font=('Consolas', 10))
        report_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Get formatted text report
        report_content = self.scheduler.get_report_text()
        report_text.insert('1.0', report_content)
        report_text.config(state=tk.DISABLED)

        # Button frame
        btn_frame = ttk.Frame(popup)
        btn_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        def save_report():
            filepath = filedialog.asksaveasfilename(
                defaultextension=".json",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
                initialfile=f"error_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
            if filepath:
                self.scheduler.save_error_report(filepath)
                messagebox.showinfo("Saved", f"Report saved to:\n{filepath}")

        def open_screenshots():
            screenshot_dir = os.path.join(os.path.dirname(__file__), 'error_screenshots')
            if os.path.exists(screenshot_dir):
                os.startfile(screenshot_dir)
            else:
                messagebox.showinfo("Info", "No screenshots folder found yet")

        ttk.Button(btn_frame, text="Save JSON Report", command=save_report).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Open Screenshots Folder", command=open_screenshots).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Close", command=popup.destroy).pack(side=tk.RIGHT, padx=5)

    def retry_selected_job(self):
        selection = self.jobs_tree.selection()
        for item in selection:
            job_id = self.jobs_tree.item(item)['values'][0]
            self.scheduler.retry_failed_job(job_id)
        self.refresh_jobs()

    def show_jobs_menu(self, event):
        selection = self.jobs_tree.selection()
        if selection:
            self.jobs_menu.post(event.x_root, event.y_root)

    def on_job_complete(self, job, success):
        """Called when a job completes"""
        self.root.after(100, self.refresh_jobs)
        self.root.after(100, self.refresh_stats)

    def refresh_all(self):
        self.refresh_folders()
        self.refresh_accounts()
        self.refresh_jobs()
        self.refresh_stats()

    def refresh_folders(self):
        self.folders_listbox.delete(0, tk.END)
        for folder in self.scheduler.video_folders:
            display = os.path.basename(folder) or folder
            self.folders_listbox.insert(tk.END, folder)

    def refresh_accounts(self):
        self.accounts_listbox.delete(0, tk.END)
        for name, acc in self.scheduler.accounts.items():
            display = f"{name} ({acc.total_posts} posts)"
            self.accounts_listbox.insert(tk.END, name)

    def refresh_jobs(self):
        # Clear tree
        for item in self.jobs_tree.get_children():
            self.jobs_tree.delete(item)

        # Add jobs (show non-success first)
        jobs_sorted = sorted(
            self.scheduler.jobs.values(),
            key=lambda j: (j.status == PostStatus.SUCCESS.value, j.id)
        )

        for job in jobs_sorted[:100]:  # Limit display
            status_display = job.status.upper()
            error_display = job.last_error[:50] if job.last_error else ""

            # Color coding
            tags = ()
            if job.status == PostStatus.SUCCESS.value:
                tags = ('success',)
            elif job.status == PostStatus.FAILED.value:
                tags = ('failed',)
            elif job.status == PostStatus.RETRYING.value:
                tags = ('retrying',)
            elif job.status == PostStatus.IN_PROGRESS.value:
                tags = ('inprogress',)

            self.jobs_tree.insert('', tk.END, values=(
                job.id,
                job.account or '-',
                status_display,
                f"{job.attempts}/{job.max_attempts}",
                error_display
            ), tags=tags)

        # Configure tag colors
        self.jobs_tree.tag_configure('success', foreground='green')
        self.jobs_tree.tag_configure('failed', foreground='red')
        self.jobs_tree.tag_configure('retrying', foreground='orange')
        self.jobs_tree.tag_configure('inprogress', foreground='blue')

    def refresh_stats(self):
        stats = self.scheduler.get_stats()

        self.stats_labels['total'].config(text=str(stats['total_jobs']))
        self.stats_labels['pending'].config(text=str(stats['pending']))
        self.stats_labels['success'].config(text=str(stats['success']), foreground='green')
        self.stats_labels['retrying'].config(text=str(stats['retrying']), foreground='orange')
        self.stats_labels['failed'].config(text=str(stats['failed']), foreground='red')

        # Update progress bar
        total = stats['total_jobs']
        if total > 0:
            completed = stats['success'] + stats['failed']
            self.progress['value'] = (completed / total) * 100
        else:
            self.progress['value'] = 0

        self.update_status_indicator()

    def update_status_indicator(self):
        if self.scheduler.running:
            if self.scheduler.paused:
                self.status_indicator.config(text="PAUSED", bg="orange")
            else:
                self.status_indicator.config(text="RUNNING", bg="green")
        else:
            self.status_indicator.config(text="STOPPED", bg="gray")

    def auto_refresh(self):
        """Auto-refresh stats every 2 seconds"""
        if self.scheduler.running:
            self.refresh_stats()
            self.refresh_jobs()
        self.root.after(2000, self.auto_refresh)

    def on_close(self):
        """Clean up on window close"""
        if self.scheduler.running:
            if messagebox.askyesno("Confirm", "Scheduler is running. Stop and exit?"):
                self.scheduler.stop()
            else:
                return
        self.root.destroy()


def main():
    root = tk.Tk()
    app = PostingDashboard(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
