// ViewModels/MainViewModel.cs
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Microsoft.Win32;
using System.Collections.ObjectModel;
using System.Threading;
using VideoLocalizer.Models;
using VideoLocalizer.Services;

namespace VideoLocalizer.ViewModels;

/// <summary>
/// MainViewModel: toàn bộ logic binding cho MainWindow
/// Kế thừa ObservableObject → tự INotifyPropertyChanged
/// </summary>
public partial class MainViewModel : ObservableObject
{
    // =====================================================================
    // SERVICES
    // =====================================================================

    /// <summary>
    /// ApiService: gọi HTTP đến Python backend.
    /// Khởi tạo với URL mặc định, có thể override từ Settings.
    /// </summary>
    public ApiService Api { get; } = new ApiService("http://localhost:8000");

    // =====================================================================
    // TASK TRACKING
    // =====================================================================

    /// <summary>ID của task đang chạy (OCR hoặc Translate)</summary>
    private string? _currentTaskId;

    /// <summary>Dùng để cancel task đang chạy khi user bấm "Hủy"</summary>
    private CancellationTokenSource? _cancelSource;

    // =====================================================================
    // VIDEO PLAYER STATE
    // =====================================================================

    /// <summary>Đường dẫn video hiện tại đang load</summary>
    [ObservableProperty]
    private string _videoPath = string.Empty;

    /// <summary>Vị trí hiện tại của video (milliseconds) — dùng để highlight sub</summary>
    [ObservableProperty]
    private long _currentPositionMs = 0;

    /// <summary>
    /// Vùng chọn OCR hiện tại (tỉ lệ 0–1).
    /// Set từ code-behind sau khi user kéo chuột trên Canvas.
    /// </summary>
    public OcrRegion OcrRegion { get; set; } = OcrRegion.Default;

    /// <summary>
    /// Kích thước VideoView control (pixel) để convert OcrRegion → pixel coords.
    /// Set từ code-behind khi VideoView SizeChanged.
    /// </summary>
    public System.Windows.Size VideoViewSize { get; set; }

    /// <summary>
    /// Kích thước nguồn video gốc (pixel). Ưu tiên dùng để convert crop gửi backend.
    /// </summary>
    public System.Windows.Size VideoSourceSize { get; set; }

    // =====================================================================
    // SUBTITLE DATA
    // =====================================================================

    /// <summary>
    /// Danh sách subtitle entries bind vào DataGrid
    /// ObservableCollection tự notify UI khi thêm/xóa item
    /// </summary>
    public ObservableCollection<SubtitleEntry> Subtitles { get; } = new();

    /// <summary>Dòng sub đang được chọn/highlighted trên DataGrid</summary>
    [ObservableProperty]
    private SubtitleEntry? _selectedSubtitle;

    /// <summary>Đường dẫn file SRT hiện tại (để save)</summary>
    [ObservableProperty]
    private string _currentSrtPath = string.Empty;

    // =====================================================================
    // TRANSLATION SETTINGS (Right panel)
    // =====================================================================

    /// <summary>
    /// Style dịch đang chọn (bind với RadioButton group)
    /// Giá trị: "lifestyle" | "review" | "ancient_drama"
    /// </summary>
    [ObservableProperty]
    private string _selectedStyle = "lifestyle";

    /// <summary>
    /// Nội dung textbox Từ điển bắt buộc (Glossary)
    /// Format mỗi dòng: "大师姐 = Đại sư tỷ"
    /// </summary>
    [ObservableProperty]
    private string _glossaryText = string.Empty;

    // =====================================================================
    // PROGRESS / STATUS
    // =====================================================================

    /// <summary>Text hiển thị trên status bar bên dưới</summary>
    [ObservableProperty]
    private string _statusMessage = "Sẵn sàng";

    /// <summary>Tiến độ task 0–100 (bind vào ProgressBar)</summary>
    [ObservableProperty]
    private int _taskProgress = 0;

    /// <summary>true khi đang chạy OCR/Translate → hiện ProgressBar, ẩn nút</summary>
    [ObservableProperty]
    private bool _isBusy = false;

    /// <summary>true khi đã kết nối được Python backend</summary>
    [ObservableProperty]
    private bool _isBackendConnected = false;

    // =====================================================================
    // COMMANDS — [RelayCommand] tự tạo ICommand property
    // =====================================================================

    /// <summary>Mở file video từ local disk rồi set VideoPath để code-behind load LibVLC</summary>
    [RelayCommand]
    private void OpenVideo()
    {
        var dialog = new OpenFileDialog
        {
            Title = "Chọn file video",
            // Filter: tên hiển thị | extension patterns
            Filter = "Video files|*.mp4;*.mkv;*.avi;*.mov;*.wmv;*.flv;*.webm|All files|*.*",
            CheckFileExists = true
        };

        // ShowDialog() trả về true khi user chọn file và bấm OK
        if (dialog.ShowDialog() == true)
        {
            VideoPath = dialog.FileName;   // code-behind sẽ watch property này
            StatusMessage = $"Đã mở: {System.IO.Path.GetFileName(dialog.FileName)}";
        }
    }

    /// <summary>Load file SRT vào DataGrid</summary>
    [RelayCommand]
    private void LoadSrt()
    {
        var dialog = new OpenFileDialog
        {
            Title = "Chọn file SRT",
            Filter = "SRT Subtitle files|*.srt|All files|*.*",
            CheckFileExists = true
        };

        if (dialog.ShowDialog() != true) return;

        try
        {
            CurrentSrtPath = dialog.FileName;
            // Parse file SRT → list entries
            var entries = SubtitleService.Parse(dialog.FileName);

            // Xóa danh sách cũ rồi thêm vào
            Subtitles.Clear();
            foreach (var entry in entries)
                Subtitles.Add(entry);

            StatusMessage = $"Đã load {entries.Count} dòng từ {System.IO.Path.GetFileName(dialog.FileName)}";
        }
        catch (Exception ex)
        {
            StatusMessage = $"Lỗi load SRT: {ex.Message}";
        }
    }

    /// <summary>Save SRT hiện tại — nếu chưa có path thì mở SaveFileDialog</summary>
    [RelayCommand]
    private void SaveSrt()
    {
        if (Subtitles.Count == 0)
        {
            StatusMessage = "Không có subtitle để lưu.";
            return;
        }

        // Nếu chưa có đường dẫn → hỏi user muốn lưu ở đâu
        if (string.IsNullOrEmpty(CurrentSrtPath))
        {
            var dialog = new SaveFileDialog
            {
                Title = "Lưu file SRT",
                Filter = "SRT Subtitle files|*.srt",
                FileName = "translated.srt"
            };
            if (dialog.ShowDialog() != true) return;
            CurrentSrtPath = dialog.FileName;
        }

        try
        {
            SubtitleService.Save(Subtitles, CurrentSrtPath);
            StatusMessage = $"Đã lưu: {System.IO.Path.GetFileName(CurrentSrtPath)}";
        }
        catch (Exception ex)
        {
            StatusMessage = $"Lỗi lưu SRT: {ex.Message}";
        }
    }

    // =====================================================================
    // SUBTITLE EDITING COMMANDS
    // =====================================================================

    /// <summary>
    /// Chèn subtitle mới TRƯỚC entry chỉ định.
    /// </summary>
    public void AddSubtitleBefore(SubtitleEntry target, SubtitleEntry newEntry)
    {
        int idx = Subtitles.IndexOf(target);
        if (idx < 0) idx = 0;
        Subtitles.Insert(idx, newEntry);
        ReIndexSubtitles();
        SelectedSubtitle = newEntry;
        StatusMessage = $"Đã thêm subtitle trước dòng {idx + 1}";
    }

    /// <summary>
    /// Chèn subtitle mới SAU entry chỉ định.
    /// </summary>
    public void AddSubtitleAfter(SubtitleEntry target, SubtitleEntry newEntry)
    {
        int idx = Subtitles.IndexOf(target);
        int insertAt = (idx >= 0) ? idx + 1 : Subtitles.Count;
        Subtitles.Insert(insertAt, newEntry);
        ReIndexSubtitles();
        SelectedSubtitle = newEntry;
        StatusMessage = $"Đã thêm subtitle sau dòng {idx + 1}";
    }

    /// <summary>
    /// Xóa subtitle entry chỉ định.
    /// </summary>
    public void DeleteSubtitle(SubtitleEntry target)
    {
        int idx = Subtitles.IndexOf(target);
        if (idx < 0) return;
        Subtitles.Remove(target);
        ReIndexSubtitles();
        // Chọn dòng kế tiếp (hoặc dòng cuối nếu xóa dòng cuối)
        if (Subtitles.Count > 0)
            SelectedSubtitle = Subtitles[Math.Min(idx, Subtitles.Count - 1)];
        StatusMessage = $"Đã xóa subtitle #{idx + 1}";
    }

    /// <summary>
    /// Đặt lại số thứ tự Index (1-based) cho tất cả subtitle sau insert/delete.
    /// </summary>
    private void ReIndexSubtitles()
    {
        for (int i = 0; i < Subtitles.Count; i++)
            Subtitles[i].Index = i + 1;
    }

    // =====================================================================
    // STEP 6: API COMMANDS (Async + SSE)
    // =====================================================================

    /// <summary>
    /// Chạy OCR pipeline trên video hiện tại.
    /// Flow: POST /api/v1/ocr → nhận task_id → stream SSE → update progress.
    /// </summary>
    [RelayCommand(CanExecute = nameof(CanRunTask))]
    private async Task RunOcr()
    {
        if (string.IsNullOrEmpty(VideoPath))
        {
            StatusMessage = "Vui lòng mở video trước.";
            return;
        }

        // Chuyển OcrRegion (tỉ lệ) -> pixel coords theo kích thước video gốc.
        // Nếu chưa đọc được size nguồn thì fallback về size hiển thị.
        var targetSize = VideoSourceSize.Width > 0 && VideoSourceSize.Height > 0
            ? VideoSourceSize
            : VideoViewSize;

        var regionPixels = targetSize.Width > 0
            ? OcrRegion.ToPixels(targetSize.Width, targetSize.Height)
            : new[] { 0, 0, 0, 0 };

        var task = await Api.StartOcrAsync(VideoPath, regionPixels);
        if (task == null) { StatusMessage = "Lỗi: Không thể bắt đầu OCR."; return; }

        await StreamTaskProgress(task.TaskId, onComplete: srtPath =>
        {
            // Load SRT vừa được tạo vào DataGrid
            if (!string.IsNullOrEmpty(srtPath))
            {
                CurrentSrtPath = srtPath;
                var entries = SubtitleService.Parse(srtPath);
                Subtitles.Clear();
                foreach (var e in entries) Subtitles.Add(e);
                StatusMessage = $"OCR hoàn tất: {entries.Count} dòng subtitle";
            }
        });
    }

    /// <summary>
    /// Dịch SRT hiện tại sang tiếng Việt.
    /// Flow: POST /api/v1/translate → nhận task_id → stream SSE → update progress.
    /// </summary>
    [RelayCommand(CanExecute = nameof(CanRunTask))]
    private async Task RunTranslate()
    {
        if (string.IsNullOrEmpty(CurrentSrtPath))
        {
            StatusMessage = "Vui lòng load file SRT trước.";
            return;
        }

        var glossary = ParseGlossary();
        var task = await Api.StartTranslateAsync(CurrentSrtPath, SelectedStyle, glossary);
        if (task == null) { StatusMessage = "Lỗi: Không thể bắt đầu dịch."; return; }

        await StreamTaskProgress(task.TaskId, onComplete: translatedPath =>
        {
            // Load SRT đã dịch vào DataGrid
            if (!string.IsNullOrEmpty(translatedPath))
            {
                CurrentSrtPath = translatedPath;
                var entries = SubtitleService.Parse(translatedPath);
                Subtitles.Clear();
                foreach (var e in entries) Subtitles.Add(e);
                StatusMessage = $"Dịch hoàn tất: {entries.Count} dòng";
            }
        });
    }

    /// <summary>Hủy task đang chạy (OCR hoặc Translate)</summary>
    [RelayCommand(CanExecute = nameof(CanCancelTask))]
    private async Task CancelCurrentTask()
    {
        if (_currentTaskId == null) return;

        // Gọi API cancel + local cancel token
        await Api.CancelTaskAsync(_currentTaskId);
        _cancelSource?.Cancel();
        StatusMessage = "Đã hủy task.";
    }

    // ─ CanExecute guards —
    /// <summary>Chỉ chạy được khi không có task nào đang chạy</summary>
    private bool CanRunTask()  => !IsBusy;
    /// <summary>Chỉ cancel được khi đang có task chạy</summary>
    private bool CanCancelTask() => IsBusy;

    // ─ Core SSE streaming logic (dùng chung cho OCR + Translate) —
    /// <summary>
    /// Subscribe SSE stream của task, tự động cập nhật TaskProgress và StatusMessage.
    /// Gọi onComplete(srtPath) khi hoàn tất.
    /// </summary>
    private async Task StreamTaskProgress(string taskId, Action<string?>? onComplete = null)
    {
        _currentTaskId = taskId;
        _cancelSource  = new CancellationTokenSource();
        var ct         = _cancelSource.Token;

        // Bật busy mode: disable các nút, hiện progress bar
        SetBusy(true);

        try
        {
            while (!ct.IsCancellationRequested)
            {
                var status = await Api.GetTaskStatusAsync(taskId, ct);
                if (status == null)
                {
                    StatusMessage = "Đang chờ backend phản hồi trạng thái...";
                    await Task.Delay(500, ct);
                    continue;
                }

                // Cập nhật progress và message trên UI
                TaskProgress = status.Progress;
                if (!string.IsNullOrWhiteSpace(status.Message))
                    StatusMessage = status.Message;

                if (status.Status == "completed")
                {
                    onComplete?.Invoke(status.Result?.SrtPath);
                    break;
                }

                if (status.Status is "failed" or "cancelled" or "error")
                {
                    var err = !string.IsNullOrWhiteSpace(status.Error)
                        ? status.Error
                        : status.Message;
                    StatusMessage = $"Lỗi: {err}";
                    break;
                }

                await Task.Delay(500, ct);
            }
        }
        catch (OperationCanceledException)
        {
            // User hủy → không làm gì thêm
        }
        catch (Exception ex)
        {
            StatusMessage = $"Lỗi kết nối: {ex.Message}";
        }
        finally
        {
            // Luôn tắt busy mode dù thành công hay thất bại
            SetBusy(false);
            _currentTaskId = null;
            _cancelSource?.Dispose();
            _cancelSource  = null;
        }
    }

    /// <summary>Bật/tắt busy mode và notify CanExecute cho các button</summary>
    private void SetBusy(bool busy)
    {
        IsBusy = busy;
        // Thông báo lại CanExecute để enable/disable buttons
        RunOcrCommand.NotifyCanExecuteChanged();
        RunTranslateCommand.NotifyCanExecuteChanged();
        CancelCurrentTaskCommand.NotifyCanExecuteChanged();
    }

    /// <summary>Check backend health rồi update IsBackendConnected</summary>
    public async Task CheckBackendHealthAsync()
    {
        IsBackendConnected = await Api.CheckHealthAsync();
        StatusMessage = IsBackendConnected
            ? "Backend đang chạy (✓)"
            : "Backend chưa chạy — hãy chạy: python main.py";
    }

    public Dictionary<string, string> ParseGlossary()
    {
        var result = new Dictionary<string, string>();
        foreach (var line in GlossaryText.Split('\n', StringSplitOptions.RemoveEmptyEntries))
        {
            var parts = line.Split('=', 2);
            if (parts.Length == 2)
            {
                var key = parts[0].Trim();
                var val = parts[1].Trim();
                if (!string.IsNullOrEmpty(key))
                    result[key] = val;
            }
        }
        return result;
    }

    /// <summary>
    /// Tự động highlight dòng sub tương ứng với vị trí video hiện tại
    /// Gọi từ DispatcherTimer 100ms trong MainWindow.xaml.cs
    /// </summary>
    public void SyncSubtitleHighlight()
    {
        var currentMs = CurrentPositionMs;
        // Tìm dòng sub đang active (startTime ≤ current < endTime)
        var active = Subtitles.FirstOrDefault(s =>
            s.StartTime.TotalMilliseconds <= currentMs &&
            currentMs < s.EndTime.TotalMilliseconds);

        if (active != null && active != SelectedSubtitle)
            SelectedSubtitle = active;
    }
}
