namespace OpenCivOne.Presentation;

/// <summary>
/// Platform-neutral 32-bit frame composed from the original indexed
/// OpenCivOne screens. Pixel values are ARGB integers whose little-endian
/// memory representation is BGRA8888.
/// </summary>
public sealed record ClassicFrame(int Width, int Height, int[] Pixels);
