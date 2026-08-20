using System.ComponentModel;
using System.Runtime.InteropServices;

namespace OpenCivOne.Platform;

internal static class ClassicDurableFileOperations
{
	public static void Move(
		string sourcePath,
		string destinationPath,
		bool overwrite)
	{
		if (!OperatingSystem.IsWindows())
		{
			File.Move(
				sourcePath,
				destinationPath,
				overwrite);
			return;
		}

		MoveFileFlags flags = MoveFileFlags.WriteThrough;
		if (overwrite)
		{
			flags |= MoveFileFlags.ReplaceExisting;
		}

		if (!MoveFileEx(
			sourcePath,
			destinationPath,
			flags))
		{
			int error = Marshal.GetLastWin32Error();
			throw new IOException(
				$"The durable move from '{sourcePath}' to '{destinationPath}' failed.",
				new Win32Exception(error));
		}
	}

	[DllImport(
		"kernel32.dll",
		EntryPoint = "MoveFileExW",
		CharSet = CharSet.Unicode,
		SetLastError = true)]
	[return: MarshalAs(UnmanagedType.Bool)]
	private static extern bool MoveFileEx(
		string existingFileName,
		string newFileName,
		MoveFileFlags flags);

	[Flags]
	private enum MoveFileFlags : uint
	{
		ReplaceExisting = 0x1,
		WriteThrough = 0x8,
	}
}
