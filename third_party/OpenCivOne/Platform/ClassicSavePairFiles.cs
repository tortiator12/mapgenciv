using System.Collections.Concurrent;
using System.Diagnostics;
using System.Text;
using OpenCivOne.Runtime;

namespace OpenCivOne.Platform;

/// <summary>
/// Keeps a Classic save state (.SVE) and its map (.MAP) on the same storage
/// side and recovers interrupted pair commits before either file is used.
/// </summary>
public sealed class ClassicSavePairFiles
{
	private const string PairJournalHeader = "PROJECT1991-SAVE-PAIR/1";
	private const string BundleJournalHeader =
		"PROJECT1991-SAVE-BUNDLE/2";
	private static readonly TimeSpan DefaultLockTimeout =
		TimeSpan.FromSeconds(2);
	private static readonly TimeSpan LockRetryDelay =
		TimeSpan.FromMilliseconds(25);
	private static readonly ConcurrentDictionary<string, object> SlotLocks =
		new(
			OperatingSystem.IsWindows()
				? StringComparer.OrdinalIgnoreCase
				: StringComparer.Ordinal);

	private readonly ClassicRuntimeOptions options;
	private readonly TimeSpan lockTimeout;

	public ClassicSavePairFiles(ClassicRuntimeOptions options)
		: this(options, DefaultLockTimeout)
	{
	}

	public ClassicSavePairFiles(
		ClassicRuntimeOptions options,
		TimeSpan lockTimeout)
	{
		this.options =
			options ?? throw new ArgumentNullException(nameof(options));

		if (lockTimeout <= TimeSpan.Zero)
		{
			throw new ArgumentOutOfRangeException(
				nameof(lockTimeout),
				"Save-pair lock timeout must be positive.");
		}

		this.lockTimeout = lockTimeout;
	}

	public ClassicSavePairPaths SelectForRead(string fileName)
	{
		string slotName = GetSlotName(fileName);
		return ExecuteWithSlotLock(
			slotName,
			() =>
			{
				RecoverSlotCore(slotName);
				return SelectForReadCore(slotName);
			});
	}

	public ClassicSaveBundlePaths SelectBundleForRead(string fileName)
	{
		string slotName = GetSlotName(fileName);
		return ExecuteWithSlotLock(
			slotName,
			() =>
			{
				RecoverSlotCore(slotName);
				return SelectBundleForReadCore(slotName);
			});
	}

	public TResult ReadPair<TResult>(
		string fileName,
		Func<ClassicSavePairPaths, TResult> reader)
	{
		ArgumentNullException.ThrowIfNull(reader);
		string slotName = GetSlotName(fileName);

		return ExecuteWithSlotLock(
			slotName,
			() =>
			{
				RecoverSlotCore(slotName);
				return reader(SelectForReadCore(slotName));
			});
	}

	public TResult ReadBundle<TResult>(
		string fileName,
		Func<ClassicSaveBundlePaths, TResult> reader)
	{
		ArgumentNullException.ThrowIfNull(reader);
		string slotName = GetSlotName(fileName);

		return ExecuteWithSlotLock(
			slotName,
			() =>
			{
				RecoverSlotCore(slotName);
				return reader(SelectBundleForReadCore(slotName));
			});
	}

	public TResult InspectBundle<TResult>(
		string fileName,
		Func<ClassicSaveBundleInspection, TResult> inspector)
	{
		ArgumentNullException.ThrowIfNull(inspector);
		string slotName = GetSlotName(fileName);

		return ExecuteWithSlotLock(
			slotName,
			() =>
			{
				RecoverSlotCore(slotName);
				return inspector(InspectBundleCore(slotName));
			});
	}

	public void WritePair(
		string fileName,
		Action<ClassicSavePairPaths> writer)
	{
		ArgumentNullException.ThrowIfNull(writer);
		string slotName = GetSlotName(fileName);

		ExecuteWithSlotLock(
			slotName,
			() =>
			{
				RecoverSlotCore(slotName);
				WritePairCore(slotName, writer);
				return true;
			});
	}

	public void WriteBundle(
		string fileName,
		Action<ClassicSaveBundlePaths> writer)
	{
		ArgumentNullException.ThrowIfNull(writer);
		string slotName = GetSlotName(fileName);

		ExecuteWithSlotLock(
			slotName,
			() =>
			{
				RecoverSlotCore(slotName);
				WriteBundleCore(slotName, writer);
				return true;
			});
	}

	private void WritePairCore(
		string slotName,
		Action<ClassicSavePairPaths> writer)
	{
		string transactionID = Guid.NewGuid().ToString("N");
		SavePairTransaction transaction =
			GetTransaction(slotName, transactionID);

		try
		{
			writer(transaction.TemporaryPair);
			FlushPairToDisk(transaction.TemporaryPair);
			CommitTemporaryPair(transaction);
		}
		finally
		{
			TryDeleteFile(transaction.TemporaryPair.StatePath);
			TryDeleteFile(transaction.TemporaryPair.MapPath);
			TryDeleteFile(transaction.JournalTemporaryPath);
		}
	}

	private void WriteBundleCore(
		string slotName,
		Action<ClassicSaveBundlePaths> writer)
	{
		string transactionID = Guid.NewGuid().ToString("N");
		SavePairTransaction transaction =
			GetTransaction(slotName, transactionID);

		try
		{
			writer(transaction.TemporaryBundle);
			FlushBundleToDisk(transaction.TemporaryBundle);
			CommitTemporaryBundle(transaction);
		}
		finally
		{
			// Once the durable journal exists, its transaction files are the
			// only material from which a later recovery can finish. A failed
			// in-call recovery must therefore leave them intact.
			if (!File.Exists(transaction.JournalPath))
			{
				TryDeleteFile(transaction.TemporaryPair.StatePath);
				TryDeleteFile(transaction.TemporaryPair.MapPath);
				TryDeleteFile(transaction.TemporaryBundle.MetadataPath);
				TryDeleteFile(transaction.JournalTemporaryPath);
			}
		}
	}

	private ClassicSavePairPaths SelectForReadCore(string slotName)
	{
		ClassicSavePairPaths savePair = GetSavePair(slotName);

		if (File.Exists(savePair.StatePath) &&
			File.Exists(savePair.MapPath))
		{
			return savePair;
		}

		if (this.options.ResourceProvider.SourceKind !=
			RuntimeResourceSourceKind.OwnerData)
		{
			return savePair;
		}

		return new ClassicSavePairPaths(
			this.options.GetResourceFilePath($"{slotName}.SVE"),
			this.options.GetResourceFilePath($"{slotName}.MAP"),
			UsesSaveDirectory: false);
	}

	private ClassicSaveBundlePaths SelectBundleForReadCore(string slotName)
	{
		ClassicSavePairPaths pair = SelectForReadCore(slotName);
		string metadataPath = pair.UsesSaveDirectory
			? this.options.GetSaveFilePath($"{slotName}.P91")
			: this.options.GetResourceFilePath($"{slotName}.P91");

		return new ClassicSaveBundlePaths(
			pair.StatePath,
			pair.MapPath,
			metadataPath,
			pair.UsesSaveDirectory);
	}

	private ClassicSaveBundleInspection InspectBundleCore(
		string slotName)
	{
		ClassicSaveBundlePaths saveBundle = new(
			this.options.GetSaveFilePath($"{slotName}.SVE"),
			this.options.GetSaveFilePath($"{slotName}.MAP"),
			this.options.GetSaveFilePath($"{slotName}.P91"),
			UsesSaveDirectory: true);

		if (File.Exists(saveBundle.StatePath) &&
			File.Exists(saveBundle.MapPath))
		{
			return new ClassicSaveBundleInspection(
				ClassicSaveBundlePresence.Complete,
				saveBundle);
		}

		if (this.options.ResourceProvider.SourceKind !=
			RuntimeResourceSourceKind.OwnerData)
		{
			return new ClassicSaveBundleInspection(
				HasAnyBundleArtifact(saveBundle)
					? ClassicSaveBundlePresence.Incomplete
					: ClassicSaveBundlePresence.Empty,
				saveBundle);
		}

		ClassicSaveBundlePaths resourceBundle = new(
			this.options.GetResourceFilePath($"{slotName}.SVE"),
			this.options.GetResourceFilePath($"{slotName}.MAP"),
			this.options.GetResourceFilePath($"{slotName}.P91"),
			UsesSaveDirectory: false);

		if (File.Exists(resourceBundle.StatePath) &&
			File.Exists(resourceBundle.MapPath))
		{
			return new ClassicSaveBundleInspection(
				ClassicSaveBundlePresence.Complete,
				resourceBundle);
		}

		if (HasAnyBundleArtifact(saveBundle))
		{
			return new ClassicSaveBundleInspection(
				ClassicSaveBundlePresence.Incomplete,
				saveBundle);
		}

		if (HasAnyBundleArtifact(resourceBundle))
		{
			return new ClassicSaveBundleInspection(
				ClassicSaveBundlePresence.Incomplete,
				resourceBundle);
		}

		return new ClassicSaveBundleInspection(
			ClassicSaveBundlePresence.Empty,
			resourceBundle);
	}

	private static bool HasAnyBundleArtifact(
		ClassicSaveBundlePaths bundle) =>
		PathExists(bundle.StatePath) ||
		PathExists(bundle.MapPath) ||
		PathExists(bundle.MetadataPath);

	private static bool PathExists(string path) =>
		File.Exists(path) || Directory.Exists(path);

	private void CommitTemporaryPair(SavePairTransaction transaction)
	{
		if (!File.Exists(transaction.TemporaryPair.StatePath) ||
			!File.Exists(transaction.TemporaryPair.MapPath))
		{
			throw new InvalidDataException(
				"Both the .SVE state and .MAP file must be written before a save can be committed.");
		}

		bool hadState = File.Exists(transaction.FinalPair.StatePath);
		bool hadMap = File.Exists(transaction.FinalPair.MapPath);

		try
		{
			if (hadState)
			{
				CopyAndFlush(
					transaction.FinalPair.StatePath,
					transaction.BackupPair.StatePath);
			}

			if (hadMap)
			{
				CopyAndFlush(
					transaction.FinalPair.MapPath,
					transaction.BackupPair.MapPath);
			}

			WriteJournalAtomically(
				transaction,
				new SavePairJournal(
					SaveTransactionKind.Pair,
					transaction.TransactionID,
					hadState,
					hadMap,
					HadMetadata: false));

			ClassicDurableFileOperations.Move(
				transaction.TemporaryPair.StatePath,
				transaction.FinalPair.StatePath,
				overwrite: true);
			ClassicDurableFileOperations.Move(
				transaction.TemporaryPair.MapPath,
				transaction.FinalPair.MapPath,
				overwrite: true);

			File.Delete(transaction.JournalPath);
			CleanupTransactionArtifacts(transaction.SlotName);
		}
		catch (Exception commitException)
		{
			try
			{
				RecoverSlotCore(transaction.SlotName);
			}
			catch (Exception recoveryException)
			{
				throw new AggregateException(
					"The Classic save pair could not be committed or recovered. Transaction files were retained.",
					commitException,
					recoveryException);
			}

			throw new IOException(
				"The Classic save pair could not be committed; a complete previous or new pair was recovered.",
				commitException);
		}
	}

	private void CommitTemporaryBundle(SavePairTransaction transaction)
	{
		if (!File.Exists(transaction.TemporaryPair.StatePath) ||
			!File.Exists(transaction.TemporaryPair.MapPath) ||
			!File.Exists(transaction.TemporaryBundle.MetadataPath))
		{
			throw new InvalidDataException(
				"The .SVE state, .MAP file, and .P91 metadata must all be written before a save bundle can be committed.");
		}

		bool hadState = File.Exists(transaction.FinalPair.StatePath);
		bool hadMap = File.Exists(transaction.FinalPair.MapPath);
		bool hadMetadata =
			File.Exists(transaction.FinalBundle.MetadataPath);

		try
		{
			if (hadState)
			{
				CopyAndFlush(
					transaction.FinalPair.StatePath,
					transaction.BackupPair.StatePath);
			}

			if (hadMap)
			{
				CopyAndFlush(
					transaction.FinalPair.MapPath,
					transaction.BackupPair.MapPath);
			}

			if (hadMetadata)
			{
				CopyAndFlush(
					transaction.FinalBundle.MetadataPath,
					transaction.BackupBundle.MetadataPath);
			}

			WriteJournalAtomically(
				transaction,
				new SavePairJournal(
					SaveTransactionKind.Bundle,
					transaction.TransactionID,
					hadState,
					hadMap,
					hadMetadata));

			ClassicDurableFileOperations.Move(
				transaction.TemporaryPair.StatePath,
				transaction.FinalPair.StatePath,
				overwrite: true);
			ClassicDurableFileOperations.Move(
				transaction.TemporaryPair.MapPath,
				transaction.FinalPair.MapPath,
				overwrite: true);
			ClassicDurableFileOperations.Move(
				transaction.TemporaryBundle.MetadataPath,
				transaction.FinalBundle.MetadataPath,
				overwrite: true);

			File.Delete(transaction.JournalPath);
			CleanupTransactionArtifacts(transaction.SlotName);
		}
		catch (Exception commitException)
		{
			try
			{
				RecoverSlotCore(transaction.SlotName);
			}
			catch (Exception recoveryException)
			{
				throw new AggregateException(
					"The Classic save bundle could not be committed or recovered. Transaction files were retained.",
					commitException,
					recoveryException);
			}

			throw new IOException(
				"The Classic save bundle could not be committed; a complete previous or new bundle was recovered.",
				commitException);
		}
	}

	private void RecoverSlotCore(string slotName)
	{
		string journalPath = GetJournalPath(slotName);

		if (Directory.Exists(journalPath))
		{
			throw new InvalidDataException(
				$"The save transaction journal path '{journalPath}' is a directory.");
		}

		if (!File.Exists(journalPath))
		{
			CleanupTransactionArtifacts(slotName);
			return;
		}

		SavePairJournal journal = ReadJournal(journalPath);
		SavePairTransaction transaction =
			GetTransaction(slotName, journal.TransactionID);

		bool hasCompleteOldPair =
			journal.HadState &&
			journal.HadMap &&
			File.Exists(transaction.BackupPair.StatePath) &&
			File.Exists(transaction.BackupPair.MapPath);
		bool hasCompleteOldBundle =
			hasCompleteOldPair &&
			(!journal.HadMetadata ||
			 File.Exists(transaction.BackupBundle.MetadataPath));

		if ((journal.Kind == SaveTransactionKind.Pair &&
			 hasCompleteOldPair) ||
			(journal.Kind == SaveTransactionKind.Bundle &&
			 hasCompleteOldBundle))
		{
			RestoreFromBackup(
				transaction.BackupPair.StatePath,
				transaction.FinalPair.StatePath,
				transaction.RestoreStatePath);
			RestoreFromBackup(
				transaction.BackupPair.MapPath,
				transaction.FinalPair.MapPath,
				transaction.RestoreMapPath);
			if (journal.Kind == SaveTransactionKind.Bundle)
			{
				RestoreMetadataShape(transaction, journal.HadMetadata);
			}

			CompleteRecovery(transaction);
			return;
		}

		bool canCompleteNewTransaction =
			journal.Kind == SaveTransactionKind.Bundle
				? CanCompleteNewBundle(transaction)
				: CanCompleteNewPair(transaction);

		if (canCompleteNewTransaction)
		{
			try
			{
				PromoteTemporaryFileIfPresent(
					transaction.TemporaryPair.StatePath,
					transaction.FinalPair.StatePath);
				PromoteTemporaryFileIfPresent(
					transaction.TemporaryPair.MapPath,
					transaction.FinalPair.MapPath);
				if (journal.Kind == SaveTransactionKind.Bundle)
				{
					PromoteTemporaryFileIfPresent(
						transaction.TemporaryBundle.MetadataPath,
						transaction.FinalBundle.MetadataPath);
				}

				if (File.Exists(transaction.FinalPair.StatePath) &&
					File.Exists(transaction.FinalPair.MapPath) &&
					(journal.Kind == SaveTransactionKind.Pair ||
					 File.Exists(transaction.FinalBundle.MetadataPath)))
				{
					CompleteRecovery(transaction);
					return;
				}
			}
			catch (IOException)
			{
				// If the new pair cannot be completed, recovery below restores
				// the exact pre-transaction file shape when possible.
			}
			catch (UnauthorizedAccessException)
			{
				// See the IOException branch above.
			}
		}

		RestoreOriginalShape(transaction, journal);
		CompleteRecovery(transaction);
	}

	private static bool CanCompleteNewBundle(
		SavePairTransaction transaction)
	{
		return CanCompleteNewPair(transaction) &&
			(File.Exists(transaction.TemporaryBundle.MetadataPath) ||
			 File.Exists(transaction.FinalBundle.MetadataPath));
	}

	private static bool CanCompleteNewPair(
		SavePairTransaction transaction)
	{
		bool hasState =
			File.Exists(transaction.TemporaryPair.StatePath) ||
			File.Exists(transaction.FinalPair.StatePath);
		bool hasMap =
			File.Exists(transaction.TemporaryPair.MapPath) ||
			File.Exists(transaction.FinalPair.MapPath);
		return hasState && hasMap;
	}

	private static void PromoteTemporaryFileIfPresent(
		string temporaryPath,
		string finalPath)
	{
		if (File.Exists(temporaryPath))
		{
			ClassicDurableFileOperations.Move(
				temporaryPath,
				finalPath,
				overwrite: true);
		}
	}

	private static void RestoreOriginalShape(
		SavePairTransaction transaction,
		SavePairJournal journal)
	{
		EnsureRequiredBackupExists(
			journal.HadState,
			transaction.BackupPair.StatePath);
		EnsureRequiredBackupExists(
			journal.HadMap,
			transaction.BackupPair.MapPath);
		if (journal.Kind == SaveTransactionKind.Bundle)
		{
			EnsureRequiredBackupExists(
				journal.HadMetadata,
				transaction.BackupBundle.MetadataPath);
		}

		if (journal.HadState)
		{
			RestoreFromBackup(
				transaction.BackupPair.StatePath,
				transaction.FinalPair.StatePath,
				transaction.RestoreStatePath);
		}
		else
		{
			if (File.Exists(transaction.FinalPair.StatePath))
			{
				File.Delete(transaction.FinalPair.StatePath);
			}
		}

		if (journal.HadMap)
		{
			RestoreFromBackup(
				transaction.BackupPair.MapPath,
				transaction.FinalPair.MapPath,
				transaction.RestoreMapPath);
		}
		else
		{
			if (File.Exists(transaction.FinalPair.MapPath))
			{
				File.Delete(transaction.FinalPair.MapPath);
			}
		}

		if (journal.Kind == SaveTransactionKind.Bundle)
		{
			RestoreMetadataShape(transaction, journal.HadMetadata);
		}
	}

	private static void RestoreMetadataShape(
		SavePairTransaction transaction,
		bool hadMetadata)
	{
		if (hadMetadata)
		{
			RestoreFromBackup(
				transaction.BackupBundle.MetadataPath,
				transaction.FinalBundle.MetadataPath,
				transaction.RestoreMetadataPath);
		}
		else if (File.Exists(transaction.FinalBundle.MetadataPath))
		{
			File.Delete(transaction.FinalBundle.MetadataPath);
		}
	}

	private static void EnsureRequiredBackupExists(
		bool required,
		string backupPath)
	{
		if (required && !File.Exists(backupPath))
		{
			throw new IOException(
				$"The required save recovery backup '{backupPath}' is missing.");
		}
	}

	private static void RestoreFromBackup(
		string backupPath,
		string finalPath,
		string restorePath)
	{
		try
		{
			// A process or power interruption can leave this scratch file
			// behind. It is never authoritative and must not make the next
			// recovery attempt fail before the durable backup is restored.
			TryDeleteFile(restorePath);
			File.Copy(backupPath, restorePath, overwrite: false);
			FlushFileToDisk(restorePath);
			ClassicDurableFileOperations.Move(
				restorePath,
				finalPath,
				overwrite: true);
		}
		finally
		{
			TryDeleteFile(restorePath);
		}
	}

	private void CompleteRecovery(SavePairTransaction transaction)
	{
		File.Delete(transaction.JournalPath);
		CleanupTransactionArtifacts(transaction.SlotName);
	}

	private void WriteJournalAtomically(
		SavePairTransaction transaction,
		SavePairJournal journal)
	{
		try
		{
			using (FileStream stream = new(
				transaction.JournalTemporaryPath,
				FileMode.CreateNew,
				FileAccess.Write,
				FileShare.None))
			using (StreamWriter writer = new(
				stream,
				new UTF8Encoding(encoderShouldEmitUTF8Identifier: false),
				leaveOpen: true))
			{
				writer.WriteLine(
					journal.Kind == SaveTransactionKind.Bundle
						? BundleJournalHeader
						: PairJournalHeader);
				writer.WriteLine(journal.TransactionID);
				writer.WriteLine(journal.HadState ? "1" : "0");
				writer.WriteLine(journal.HadMap ? "1" : "0");
				if (journal.Kind == SaveTransactionKind.Bundle)
				{
					writer.WriteLine(journal.HadMetadata ? "1" : "0");
				}

				writer.Flush();
				stream.Flush(flushToDisk: true);
			}

			ClassicDurableFileOperations.Move(
				transaction.JournalTemporaryPath,
				transaction.JournalPath,
				overwrite: false);
		}
		finally
		{
			TryDeleteFile(transaction.JournalTemporaryPath);
		}
	}

	private static SavePairJournal ReadJournal(string journalPath)
	{
		using FileStream stream = new(
			journalPath,
			FileMode.Open,
			FileAccess.Read,
			FileShare.Read);
		using StreamReader reader = new(
			stream,
			Encoding.UTF8,
			detectEncodingFromByteOrderMarks: true);

		string? header = reader.ReadLine();
		string? transactionID = reader.ReadLine();
		string? hadState = reader.ReadLine();
		string? hadMap = reader.ReadLine();
		string? hadMetadata = header == BundleJournalHeader
			? reader.ReadLine()
			: null;
		string? unexpected = reader.ReadLine();

		bool validHeader =
			header == PairJournalHeader ||
			header == BundleJournalHeader;
		bool validMetadata =
			header == PairJournalHeader
				? hadMetadata is null
				: TryParseJournalBoolean(
					hadMetadata,
					out _);

		if (!validHeader ||
			transactionID is null ||
			!Guid.TryParseExact(transactionID, "N", out _) ||
			!TryParseJournalBoolean(hadState, out bool parsedHadState) ||
			!TryParseJournalBoolean(hadMap, out bool parsedHadMap) ||
			!validMetadata ||
			unexpected is not null)
		{
			throw new InvalidDataException(
				$"The save transaction journal '{journalPath}' is invalid.");
		}

		bool parsedHadMetadata = false;
		if (header == BundleJournalHeader)
		{
			TryParseJournalBoolean(
				hadMetadata,
				out parsedHadMetadata);
		}

		return new SavePairJournal(
			header == BundleJournalHeader
				? SaveTransactionKind.Bundle
				: SaveTransactionKind.Pair,
			transactionID,
			parsedHadState,
			parsedHadMap,
			parsedHadMetadata);
	}

	private static bool TryParseJournalBoolean(
		string? value,
		out bool result)
	{
		if (value == "1")
		{
			result = true;
			return true;
		}

		result = false;
		return value == "0";
	}

	private void CleanupTransactionArtifacts(string slotName)
	{
		if (!Directory.Exists(this.options.SavePath))
		{
			return;
		}

		string prefix = $".{slotName}.";
		foreach (string path in Directory.EnumerateFiles(
			this.options.SavePath))
		{
			string fileName = Path.GetFileName(path);
			if (fileName.StartsWith(prefix, PathComparison) &&
				IsTransactionArtifact(fileName))
			{
				TryDeleteFile(path);
			}
		}
	}

	private static bool IsTransactionArtifact(string fileName)
	{
		return fileName.EndsWith(".SVE.tmp", PathComparison) ||
			fileName.EndsWith(".MAP.tmp", PathComparison) ||
			fileName.EndsWith(".P91.tmp", PathComparison) ||
			fileName.EndsWith(".SVE.bak", PathComparison) ||
			fileName.EndsWith(".MAP.bak", PathComparison) ||
			fileName.EndsWith(".P91.bak", PathComparison) ||
			fileName.EndsWith(".SVE.restore.tmp", PathComparison) ||
			fileName.EndsWith(".MAP.restore.tmp", PathComparison) ||
			fileName.EndsWith(".P91.restore.tmp", PathComparison) ||
			(fileName.Contains(".txn-", PathComparison) &&
			 fileName.EndsWith(".tmp", PathComparison));
	}

	private static void FlushBundleToDisk(ClassicSaveBundlePaths bundle)
	{
		FlushPairToDisk(bundle.Pair);
		if (!File.Exists(bundle.MetadataPath))
		{
			throw new InvalidDataException(
				"The temporary .P91 metadata file must exist before flushing.");
		}

		FlushFileToDisk(bundle.MetadataPath);
	}

	private static void FlushPairToDisk(ClassicSavePairPaths pair)
	{
		if (!File.Exists(pair.StatePath) ||
			!File.Exists(pair.MapPath))
		{
			throw new InvalidDataException(
				"Both temporary save-pair files must exist before flushing.");
		}

		FlushFileToDisk(pair.StatePath);
		FlushFileToDisk(pair.MapPath);
	}

	private static void CopyAndFlush(string sourcePath, string destinationPath)
	{
		File.Copy(sourcePath, destinationPath, overwrite: false);
		FlushFileToDisk(destinationPath);
	}

	private static void FlushFileToDisk(string path)
	{
		using FileStream stream = new(
			path,
			FileMode.Open,
			FileAccess.ReadWrite,
			FileShare.Read);
		stream.Flush(flushToDisk: true);
	}

	private TResult ExecuteWithSlotLock<TResult>(
		string slotName,
		Func<TResult> operation)
	{
		Directory.CreateDirectory(this.options.SavePath);
		string lockPath =
			this.options.GetSaveFilePath($".{slotName}.lock");
		object inProcessLock =
			SlotLocks.GetOrAdd(lockPath, static _ => new object());

		lock (inProcessLock)
		{
			using FileStream lockHandle = AcquireSlotLock(lockPath);
			return operation();
		}
	}

	private FileStream AcquireSlotLock(string lockPath)
	{
		Stopwatch stopwatch = Stopwatch.StartNew();
		IOException? lastException = null;

		while (stopwatch.Elapsed < this.lockTimeout)
		{
			try
			{
				return new FileStream(
					lockPath,
					FileMode.OpenOrCreate,
					FileAccess.ReadWrite,
					FileShare.None);
			}
			catch (IOException ex)
			{
				lastException = ex;
			}

			TimeSpan remaining = this.lockTimeout - stopwatch.Elapsed;
			if (remaining > TimeSpan.Zero)
			{
				Thread.Sleep(
					remaining < LockRetryDelay
						? remaining
						: LockRetryDelay);
			}
		}

		throw new TimeoutException(
			$"Timed out waiting for the Classic save lock '{lockPath}'.",
			lastException);
	}

	private SavePairTransaction GetTransaction(
		string slotName,
		string transactionID)
	{
		ClassicSaveBundlePaths finalBundle =
			GetSaveBundle(slotName);
		ClassicSaveBundlePaths temporaryBundle = new(
			this.options.GetSaveFilePath(
				$".{slotName}.{transactionID}.SVE.tmp"),
			this.options.GetSaveFilePath(
				$".{slotName}.{transactionID}.MAP.tmp"),
			this.options.GetSaveFilePath(
				$".{slotName}.{transactionID}.P91.tmp"),
			UsesSaveDirectory: true);
		ClassicSaveBundlePaths backupBundle = new(
			this.options.GetSaveFilePath(
				$".{slotName}.{transactionID}.SVE.bak"),
			this.options.GetSaveFilePath(
				$".{slotName}.{transactionID}.MAP.bak"),
			this.options.GetSaveFilePath(
				$".{slotName}.{transactionID}.P91.bak"),
			UsesSaveDirectory: true);

		return new SavePairTransaction(
			slotName,
			transactionID,
			finalBundle,
			temporaryBundle,
			backupBundle,
			GetJournalPath(slotName),
			this.options.GetSaveFilePath(
				$".{slotName}.txn-{transactionID}.tmp"),
			this.options.GetSaveFilePath(
				$".{slotName}.{transactionID}.SVE.restore.tmp"),
			this.options.GetSaveFilePath(
				$".{slotName}.{transactionID}.MAP.restore.tmp"),
			this.options.GetSaveFilePath(
				$".{slotName}.{transactionID}.P91.restore.tmp"));
	}

	private ClassicSavePairPaths GetSavePair(string slotName)
	{
		return new ClassicSavePairPaths(
			this.options.GetSaveFilePath($"{slotName}.SVE"),
			this.options.GetSaveFilePath($"{slotName}.MAP"),
			UsesSaveDirectory: true);
	}

	private ClassicSaveBundlePaths GetSaveBundle(string slotName)
	{
		ClassicSavePairPaths pair = GetSavePair(slotName);
		return new ClassicSaveBundlePaths(
			pair.StatePath,
			pair.MapPath,
			this.options.GetSaveFilePath($"{slotName}.P91"),
			UsesSaveDirectory: true);
	}

	private string GetJournalPath(string slotName)
	{
		return this.options.GetSaveFilePath($".{slotName}.txn");
	}

	private static string GetSlotName(string fileName)
	{
		if (string.IsNullOrWhiteSpace(fileName) ||
			fileName.IndexOfAny(
				[
					.. Path.GetInvalidFileNameChars(),
					Path.DirectorySeparatorChar,
					Path.AltDirectorySeparatorChar,
					'\\',
					'/',
					':'
				]) >= 0)
		{
			throw new ArgumentException(
				"A plain Classic save file name is required.",
				nameof(fileName));
		}

		string extension = Path.GetExtension(fileName);
		if (extension.Length > 0 &&
			!extension.Equals(".SVE", StringComparison.OrdinalIgnoreCase))
		{
			throw new ArgumentException(
				"Classic save pairs must be addressed by slot name or .SVE file name.",
				nameof(fileName));
		}

		string slotName = Path.GetFileNameWithoutExtension(fileName);
		if (string.IsNullOrWhiteSpace(slotName) || slotName is "." or "..")
		{
			throw new ArgumentException(
				"A valid Classic save slot name is required.",
				nameof(fileName));
		}

		return slotName.ToUpperInvariant();
	}

	private static void TryDeleteFile(string path)
	{
		try
		{
			File.Delete(path);
		}
		catch (IOException)
		{
		}
		catch (UnauthorizedAccessException)
		{
		}
	}

	private static StringComparison PathComparison =>
		OperatingSystem.IsWindows()
			? StringComparison.OrdinalIgnoreCase
			: StringComparison.Ordinal;

	private sealed record SavePairTransaction(
		string SlotName,
		string TransactionID,
		ClassicSaveBundlePaths FinalBundle,
		ClassicSaveBundlePaths TemporaryBundle,
		ClassicSaveBundlePaths BackupBundle,
		string JournalPath,
		string JournalTemporaryPath,
		string RestoreStatePath,
		string RestoreMapPath,
		string RestoreMetadataPath)
	{
		public ClassicSavePairPaths FinalPair => this.FinalBundle.Pair;

		public ClassicSavePairPaths TemporaryPair =>
			this.TemporaryBundle.Pair;

		public ClassicSavePairPaths BackupPair => this.BackupBundle.Pair;
	}

	private sealed record SavePairJournal(
		SaveTransactionKind Kind,
		string TransactionID,
		bool HadState,
		bool HadMap,
		bool HadMetadata);

	private enum SaveTransactionKind
	{
		Pair,
		Bundle
	}
}

public readonly record struct ClassicSavePairPaths(
	string StatePath,
	string MapPath,
	bool UsesSaveDirectory);
