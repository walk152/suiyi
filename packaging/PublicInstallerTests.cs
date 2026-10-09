using System;
using System.IO;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;

// Compile with Setup.cs and /main:PublicInstallerTests. No installation,
// registration, shortcut operations, or live application cleanup is invoked.
static class PublicInstallerTests {
    const string Identity = "Suiyi-0.2-offline-20261002";
    const string Marker = "suiyi-install-manifest.txt";

    static object Invoke(string method, params object[] values) {
        var target = typeof(Setup).GetMethod(method, BindingFlags.NonPublic | BindingFlags.Static);
        if (target == null) throw new Exception("Missing installer method: " + method);
        try { return target.Invoke(null, values); }
        catch (TargetInvocationException error) { throw error.InnerException ?? error; }
    }

    static void Require(bool condition, string message) {
        if (!condition) throw new Exception(message);
    }

    static void RejectPath(string root, string relative) {
        bool rejected = false;
        try { Invoke("SafePath", root, relative); }
        catch (IOException) { rejected = true; }
        Require(rejected, "Unsafe path accepted: " + relative);
    }

    static void WriteFixture(string root, string relative) {
        string path = Path.Combine(root, relative);
        Directory.CreateDirectory(Path.GetDirectoryName(path));
        File.WriteAllText(path, "fixture:" + relative);
    }

    static int Main() {
        // The compiler output lives in ignored packaging/public-v05. Keep every
        // fixture beside it, and leave it available for inspection after tests.
        string parent = Path.GetFullPath(Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location));
        string root = Path.GetFullPath(Path.Combine(parent, "installer-fixtures-" + Guid.NewGuid().ToString("N")));
        Require(root.StartsWith(parent.TrimEnd('\\') + "\\", StringComparison.OrdinalIgnoreCase), "Fixture root escaped");
        Directory.CreateDirectory(root);
        string oldLog = Setup.Log;
        Setup.Log = Path.Combine(root, "test-setup.log");
        try {
            string optional = @"models\whisper-turbo\model.bin";
            string[] previous = { Identity, "old.dll", @"old-component\unused.dll", "current.dll", optional };
            foreach (string name in new[] { "old.dll", @"old-component\unused.dll", "current.dll",
                                             "new.dll", "personal.txt", optional, @"models\personal-model.bin" })
                WriteFixture(root, name);
            string personalBefore = File.ReadAllText(Path.Combine(root, "personal.txt"));
            string optionalBefore = File.ReadAllText(Path.Combine(root, optional));
            File.WriteAllLines(Path.Combine(root, Marker), previous);
            var current = new HashSet<string>(StringComparer.OrdinalIgnoreCase) { "CURRENT.dll", "new.dll" };
            Invoke("WriteInstallManifest", root, current);
            Invoke("RemoveSupersededProgramFiles", root, previous, current);
            Require(!File.Exists(Path.Combine(root, "old.dll")), "Superseded root component retained");
            Require(!File.Exists(Path.Combine(root, @"old-component\unused.dll")), "Superseded nested component retained");
            foreach (string name in new[] { "current.dll", "new.dll", "personal.txt", optional, @"models\personal-model.bin" })
                Require(File.Exists(Path.Combine(root, name)), "Preserved file missing: " + name);
            Require(File.ReadAllText(Path.Combine(root, "personal.txt")) == personalBefore, "Personal content changed");
            Require(File.ReadAllText(Path.Combine(root, optional)) == optionalBefore, "Optional model content changed");
            string[] manifest = File.ReadAllLines(Path.Combine(root, Marker));
            Require(manifest[0] == Identity, "Ownership identity changed");
            var owned = new HashSet<string>(manifest.Skip(1), StringComparer.OrdinalIgnoreCase);
            Require(owned.SetEquals(new[] { "current.dll", "new.dll", optional }), "Post-upgrade ownership manifest differs");
            foreach (string invalid in new[] { @"..\outside.txt", "../outside.txt", @"nested\..\..\outside.txt",
                @"\outside.txt", @"\\server\share\outside.txt", "owned.txt:stream", Path.GetFullPath(Path.Combine(root, "current.dll")) })
                RejectPath(root, invalid);
            string sibling = Path.Combine(parent, Path.GetFileName(root) + "-sibling");
            Directory.CreateDirectory(sibling);
            File.WriteAllText(Path.Combine(sibling, "outside.txt"), "untouched");
            RejectPath(root, "..\\" + Path.GetFileName(sibling) + "\\outside.txt");
            Require(File.ReadAllText(Path.Combine(sibling, "outside.txt")) == "untouched", "Sibling fixture changed");

            string foreign = Path.Combine(root, "foreign-directory");
            Directory.CreateDirectory(foreign);
            File.WriteAllText(Path.Combine(foreign, "personal.txt"), "untouched");
            bool refused = false;
            try { Invoke("ValidateRoot", foreign); }
            catch (IOException) { refused = true; }
            Require(refused, "Non-empty unowned install directory accepted");
            string invalidManifestRoot = Path.Combine(root, "invalid-manifest");
            Directory.CreateDirectory(invalidManifestRoot);
            File.WriteAllText(Path.Combine(invalidManifestRoot, Marker), "another-project\nprivate.txt\n");
            refused = false;
            try { Invoke("WriteInstallManifest", invalidManifestRoot, new[] { "new.dll" }); }
            catch (IOException) { refused = true; }
            Require(refused, "Foreign ownership marker accepted");
            Console.WriteLine("PASS: obsolete owned files removed; current files, personal files and optional models preserved; unsafe paths and foreign directories rejected. Fixture: " + root);
            return 0;
        } catch (Exception error) {
            Console.Error.WriteLine(error);
            return 1;
        } finally {
            Setup.Log = oldLog;
        }
    }
}
