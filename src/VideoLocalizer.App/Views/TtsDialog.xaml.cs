// Views/TtsDialog.xaml.cs
// Code-behind cho dialog tạo giọng nói độc lập.
// Dùng ApiService.SynthesizeTextAsync → POST /api/v1/tts/synthesize
// Audio phát trực tiếp qua MediaPlayer từ URL stream backend.

using System.Collections.ObjectModel;
using System.Diagnostics;
using System.Net.Http;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using VideoLocalizer.Models;
using VideoLocalizer.Services;

namespace VideoLocalizer.Views;

/// <summary>
/// Item đại diện cho một audio đã được tạo, hiển thị trong ListView.
/// </summary>
public class TtsAudioItem
{
    public string AudioFilename { get; set; } = string.Empty;
    public string AudioPath     { get; set; } = string.Empty;
    public string Text          { get; set; } = string.Empty;
    public string VoiceId       { get; set; } = string.Empty;
    public double SpeechRate    { get; set; }
}

public partial class TtsDialog : Wpf.Ui.Controls.FluentWindow
{
    // ── Dependencies ──
    private readonly ApiService _api;

    // ── State ──
    private readonly ObservableCollection<TtsAudioItem> _audioItems = new();
    private MediaPlayer? _mediaPlayer;
    private bool _isSynthesizing;

    public TtsDialog(ApiService api)
    {
        InitializeComponent();
        _api = api;

        // Bind ListView ItemsSource
        LvAudioList.ItemsSource = _audioItems;

        // Cập nhật counter khi collection thay đổi
        _audioItems.CollectionChanged += (_, _) =>
            TxtAudioCount.Text = $" ({_audioItems.Count})";

        // Focus text input khi mở
        Loaded += async (_, _) =>
        {
            await LoadVoicesAsync();
            TxtInput.Focus();
        };

        // Khởi tạo MediaPlayer để phát audio
        _mediaPlayer = new MediaPlayer();
        _mediaPlayer.MediaEnded += (_, _) => SetStatus("✅ Phát xong.", false);
        _mediaPlayer.MediaFailed += (_, e) => SetStatus($"❌ Lỗi phát: {e.ErrorException?.Message}", false);
    }

    // ─────────────────────────────────────────────────────────────
    // Voice loading
    // ─────────────────────────────────────────────────────────────

    private async Task LoadVoicesAsync()
    {
        try
        {
            SetStatus("Đang tải danh sách giọng đọc...", true);
            var voices = await _api.GetVoiceClonesAsync();

            CboVoice.ItemsSource   = voices;
            CboVoice.DisplayMemberPath = "Name";
            CboVoice.SelectedValuePath = "Id";

            if (voices.Count > 0)
                CboVoice.SelectedIndex = 0;

            UpdateGenerateButtonState();
            SetStatus(voices.Count > 0
                ? $"Tìm thấy {voices.Count} giọng đọc."
                : "⚠️ Không tìm thấy voice clone nào trong thư mục voice_clones.", false);
        }
        catch (Exception ex)
        {
            SetStatus($"❌ Không thể tải danh sách giọng: {ex.Message}", false);
        }
    }

    private async void BtnRefreshVoices_Click(object sender, RoutedEventArgs e)
        => await LoadVoicesAsync();

    // ─────────────────────────────────────────────────────────────
    // Speed slider
    // ─────────────────────────────────────────────────────────────

    private void SliderSpeed_ValueChanged(object sender, RoutedPropertyChangedEventArgs<double> e)
    {
        if (TxtSpeedValue != null)
            TxtSpeedValue.Text = $"{e.NewValue:F1}x";
    }

    // ─────────────────────────────────────────────────────────────
    // Text input — Ctrl+Enter shortcut
    // ─────────────────────────────────────────────────────────────

    private void TxtInput_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Return && Keyboard.Modifiers == ModifierKeys.Control)
        {
            e.Handled = true;
            BtnGenerate_Click(sender, e);
        }
    }

    private void UpdateGenerateButtonState()
    {
        BtnGenerate.IsEnabled = !_isSynthesizing
                                && CboVoice.SelectedItem != null
                                && !string.IsNullOrWhiteSpace(TxtInput?.Text);
    }

    // ─────────────────────────────────────────────────────────────
    // Generate button — gọi API và thêm vào danh sách
    // ─────────────────────────────────────────────────────────────

    private async void BtnGenerate_Click(object sender, RoutedEventArgs e)
    {
        var text = TxtInput.Text.Trim();
        if (string.IsNullOrEmpty(text))
        {
            SetStatus("⚠️ Hãy nhập văn bản trước.", false);
            TxtInput.Focus();
            return;
        }

        if (CboVoice.SelectedItem is not VoiceClone voice)
        {
            SetStatus("⚠️ Hãy chọn giọng đọc.", false);
            return;
        }

        var speechRate = SliderSpeed.Value;

        _isSynthesizing = true;
        UpdateGenerateButtonState();
        ProgressRing.Visibility = Visibility.Visible;
        SetStatus($"⏳ Đang tổng hợp giọng nói... ({text.Length} ký tự)", true);

        try
        {
            var result = await _api.SynthesizeTextAsync(
                text:        text,
                voiceId:     voice.Id,
                speechRate:  speechRate);

            if (result == null)
            {
                SetStatus("❌ Backend không trả về kết quả.", false);
                return;
            }

            // Thêm vào đầu danh sách để thấy ngay
            _audioItems.Insert(0, new TtsAudioItem
            {
                AudioFilename = result.AudioFilename,
                AudioPath     = result.AudioPath,
                Text          = result.Text.Length > 80
                                    ? result.Text[..77] + "..."
                                    : result.Text,
                VoiceId       = result.VoiceId,
                SpeechRate    = result.SpeechRate,
            });

            LvAudioList.SelectedIndex = 0;
            SetStatus($"✅ Tạo xong: {result.AudioFilename}", false);

            // Tự phát luôn audio vừa tạo
            PlayAudio(result.AudioFilename);
        }
        catch (HttpRequestException ex) when (ex.StatusCode == System.Net.HttpStatusCode.UnprocessableEntity)
        {
            SetStatus($"❌ Lỗi đầu vào: {ex.Message}", false);
        }
        catch (Exception ex)
        {
            SetStatus($"❌ Lỗi: {ex.Message}", false);
        }
        finally
        {
            _isSynthesizing = false;
            ProgressRing.Visibility = Visibility.Collapsed;
            UpdateGenerateButtonState();
        }
    }

    // ─────────────────────────────────────────────────────────────
    // Play audio — phát qua MediaPlayer từ URL backend
    // ─────────────────────────────────────────────────────────────

    private void PlayAudio(string filename)
    {
        try
        {
            _mediaPlayer?.Stop();
            var url = _api.GetAudioStreamUrl(filename);
            _mediaPlayer?.Open(new Uri(url));
            _mediaPlayer?.Play();
            SetStatus($"▶️ Đang phát: {filename}", false);
        }
        catch (Exception ex)
        {
            SetStatus($"❌ Không thể phát audio: {ex.Message}", false);
        }
    }

    private void BtnPlayAudio_Click(object sender, RoutedEventArgs e)
    {
        if (sender is System.Windows.Controls.Button btn && btn.Tag is string filename)
            PlayAudio(filename);
    }

    // ─────────────────────────────────────────────────────────────
    // Open folder
    // ─────────────────────────────────────────────────────────────

    private void BtnOpenFolder_Click(object sender, RoutedEventArgs e)
    {
        if (sender is System.Windows.Controls.Button btn && btn.Tag is string audioPath)
        {
            try
            {
                var dir = System.IO.Path.GetDirectoryName(audioPath);
                if (dir != null && System.IO.Directory.Exists(dir))
                    Process.Start("explorer.exe", $"/select,\"{audioPath}\"");
                else
                    SetStatus($"⚠️ Không tìm thấy thư mục: {dir}", false);
            }
            catch (Exception ex)
            {
                SetStatus($"❌ Không thể mở thư mục: {ex.Message}", false);
            }
        }
    }

    // ─────────────────────────────────────────────────────────────
    // Clear list / Close
    // ─────────────────────────────────────────────────────────────

    private void BtnClearList_Click(object sender, RoutedEventArgs e)
    {
        _mediaPlayer?.Stop();
        _audioItems.Clear();
        SetStatus("Đã xóa danh sách.", false);
    }

    private void BtnClose_Click(object sender, RoutedEventArgs e)
    {
        _mediaPlayer?.Stop();
        Close();
    }

    protected override void OnClosed(EventArgs e)
    {
        _mediaPlayer?.Stop();
        _mediaPlayer?.Close();
        _mediaPlayer = null;
        base.OnClosed(e);
    }

    // ─────────────────────────────────────────────────────────────
    // Status helper
    // ─────────────────────────────────────────────────────────────

    private void SetStatus(string message, bool showSpinner)
    {
        TxtStatus.Text              = message;
        ProgressRing.Visibility     = showSpinner ? Visibility.Visible : Visibility.Collapsed;
    }
}
