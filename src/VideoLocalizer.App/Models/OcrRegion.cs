// Models/OcrRegion.cs
// Lưu vùng chọn OCR (Region of Interest) trên video
namespace VideoLocalizer.Models;

/// <summary>
/// Đại diện cho vùng crop để OCR hardsub.
/// Tọa độ dùng tỉ lệ 0.0–1.0 (relative so với kích thước video)
/// để không bị ảnh hưởng khi resize cửa sổ.
///
/// VD: Subtitle thường nằm ở 80% chiều cao → Y = 0.8, H = 0.15
/// </summary>
public class OcrRegion
{
    /// <summary>Tọa độ X tính từ trái (0.0 = trái, 1.0 = phải)</summary>
    public double X { get; set; } = 0.0;

    /// <summary>Tọa độ Y tính từ trên (0.0 = trên, 1.0 = dưới)</summary>
    public double Y { get; set; } = 0.8;

    /// <summary>Chiều rộng vùng chọn (tỉ lệ)</summary>
    public double W { get; set; } = 1.0;

    /// <summary>Chiều cao vùng chọn (tỉ lệ)</summary>
    public double H { get; set; } = 0.15;

    /// <summary>
    /// Tính tọa độ pixel thực tế từ kích thước control VideoView.
    /// Dùng để gửi lên backend (backend cần pixel coord).
    /// </summary>
    /// <param name="controlWidth">Chiều rộng VideoView control (pixel)</param>
    /// <param name="controlHeight">Chiều cao VideoView control (pixel)</param>
    /// <returns>[X, Y, Width, Height] dạng pixel</returns>
    public int[] ToPixels(double controlWidth, double controlHeight)
    {
        return [
            (int)(X * controlWidth),
            (int)(Y * controlHeight),
            (int)(W * controlWidth),
            (int)(H * controlHeight)
        ];
    }

    /// <summary>
    /// Tạo OcrRegion từ tọa độ pixel (dùng khi user kéo chuột trên canvas)
    /// </summary>
    public static OcrRegion FromPixels(
        double pxX, double pxY, double pxW, double pxH,
        double controlWidth, double controlHeight)
    {
        return new OcrRegion
        {
            X = pxX / controlWidth,
            Y = pxY / controlHeight,
            W = pxW / controlWidth,
            H = pxH / controlHeight
        };
    }

    /// <summary>
    /// Vùng mặc định: full width, 15% phần dưới (vị trí subtitle thường)
    /// </summary>
    public static OcrRegion Default => new()
    {
        X = 0.0, Y = 0.80, W = 1.0, H = 0.15
    };

    public override string ToString() =>
        $"({X:P0}, {Y:P0}) {W:P0}×{H:P0}";
}
