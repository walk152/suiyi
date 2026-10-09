using System;
using System.IO;
using System.IO.Compression;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Win32;

static class Setup {
    const string Key = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\Suiyi";
    const string Marker = "suiyi-install-manifest.txt";
    const string Identity = "Suiyi-0.2-offline-20261002";
    public static string DefaultDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), @"Programs\Suiyi");
    public static string Log = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), @"Suiyi\setup.log");
    static void WriteLog(string text) { Directory.CreateDirectory(Path.GetDirectoryName(Log)); File.AppendAllText(Log,DateTime.Now.ToString("s")+" "+text+Environment.NewLine); }
    [STAThread] static int Main(string[] args) {
        Application.EnableVisualStyles();
        bool quiet=args.Contains("/quiet");
        try {
            if(args.Length>=2 && args[0]=="/remove") {
                string parent=args.FirstOrDefault(a=>a.StartsWith("/parent="));
                if(parent!=null) {try {using(var p=Process.GetProcessById(int.Parse(parent.Substring(8)))) {if(!p.WaitForExit(10000)) throw new IOException("卸载入口仍在运行，请重试。");}} catch(ArgumentException) {}}
                Remove(args[1],quiet); return 0;
            }
            if(args.Contains("/uninstall") || Path.GetFileName(Application.ExecutablePath).Equals("Uninstall.exe",StringComparison.OrdinalIgnoreCase)) {
                string root=Path.GetDirectoryName(Application.ExecutablePath);
                if(!quiet && MessageBox.Show("卸载随译程序和模型？个人设置将保留，游戏文件不受影响。", "卸载随译",MessageBoxButtons.YesNo,MessageBoxIcon.Question)!=DialogResult.Yes) return 0;
                EnsureStopped(root);
                string helper=Path.Combine(Path.GetTempPath(),"Suiyi-Uninstall-"+Guid.NewGuid().ToString("N")+".exe");
                File.Copy(Application.ExecutablePath,helper);
                Process.Start(new ProcessStartInfo(helper,"/remove \""+root+"\" /parent="+Process.GetCurrentProcess().Id+(quiet?" /quiet":"")) { UseShellExecute=true });
                return 0;
            }
            if(quiet) {
                string dir=args.FirstOrDefault(a=>a.StartsWith("/dir=",StringComparison.OrdinalIgnoreCase));
                bool verify=args.Contains("/verify-extract");
                if(verify && dir==null) throw new IOException("验证解压必须指定独立目录。");
                if(verify) Log=Path.Combine(Path.GetTempPath(),"Suiyi-Verify-"+Guid.NewGuid().ToString("N")+".log");
                if(!verify && !args.Contains("/accept-licenses")) throw new IOException("静默安装请先阅读公开版许可，并使用 /accept-licenses 明确接受。");
                Install(dir==null?DefaultDir:dir.Substring(5),(p,s)=>{},args.Contains("/desktop"),!verify); return 0;
            }
            Application.Run(new InstallForm()); return 0;
        } catch(Exception e) {
            WriteLog(e.ToString());
            if(!quiet) MessageBox.Show(e.Message+"\n\n日志："+Log,"随译安装失败",MessageBoxButtons.OK,MessageBoxIcon.Error);
            return 1;
        }
    }
    public static string LicenseText() {
        using(var stream=System.Reflection.Assembly.GetExecutingAssembly().GetManifestResourceStream("PublicTerms")) {
            if(stream==null) throw new IOException("安装包缺少许可材料。");
            using(var reader=new StreamReader(stream,Encoding.UTF8))return reader.ReadToEnd();
        }
    }
    static void EnsureStopped(string root) {
        Mutex m;
        if(root.Equals(DefaultDir,StringComparison.OrdinalIgnoreCase) && Mutex.TryOpenExisting(@"Local\SuiyiLocalSubtitlePrototype",out m)) {
            m.Dispose(); throw new IOException("随译仍在运行。请先从随译托盘菜单选择“退出”，再继续。");
        }
        string target=SafePath(root,"Suiyi.exe");
        foreach(var process in Process.GetProcessesByName("Suiyi")) using(process) {
            try {if(target.Equals(process.MainModule.FileName,StringComparison.OrdinalIgnoreCase)) throw new IOException("目标位置的随译仍在运行，请先退出后再安装。");}
            catch(InvalidOperationException) {} catch(System.ComponentModel.Win32Exception) {throw new IOException("无法确认随译进程位置，请退出随译后再试。");}
        }
    }
    static string SafePath(string root,string relative) {
        if(Path.IsPathRooted(relative) || relative.Contains(":")) throw new IOException("非法安装文件路径。");
        string full=Path.GetFullPath(Path.Combine(root,relative.Replace('/',Path.DirectorySeparatorChar)));
        if(!full.StartsWith(root.TrimEnd('\\')+"\\",StringComparison.OrdinalIgnoreCase)) throw new IOException("安装文件越界。");
        string p=full;
        while(p!=null) {
            if((Directory.Exists(p)||File.Exists(p)) && (File.GetAttributes(p)&FileAttributes.ReparsePoint)!=0) throw new IOException("安装目录不能包含目录链接："+p);
            p=Path.GetDirectoryName(p);
        }
        return full;
    }
    static string ValidateRoot(string target) {
        string root=Path.GetFullPath(target).TrimEnd('\\');
        if(root.Length<5 || root.Equals(Path.GetPathRoot(root).TrimEnd('\\'),StringComparison.OrdinalIgnoreCase)) throw new IOException("请选择独立的随译安装文件夹。");
        SafePath(root,Marker);
        if(Directory.Exists(root) && Directory.EnumerateFileSystemEntries(root).Any() && !File.Exists(Path.Combine(root,Marker)))
            throw new IOException("请选择空文件夹或已安装随译的文件夹，避免覆盖其他文件。");
        return root;
    }
    static void WriteInstallManifest(string root,IEnumerable<string> installed) {
        string manifest=Path.Combine(root,Marker);
        var names=new HashSet<string>(installed,StringComparer.OrdinalIgnoreCase);
        if(File.Exists(manifest)) {
            var previous=File.ReadAllLines(manifest,Encoding.UTF8);
            if(previous.Length<1 || previous[0]!=Identity) throw new IOException("已有安装清单无效，已取消升级。");
            foreach(string name in previous.Skip(1)) {SafePath(root,name);names.Add(name);}
        }
        File.WriteAllLines(manifest,(new[]{Identity}).Concat(names),Encoding.UTF8);
    }
    static void CompressInstalledFiles(string root,Action<int,string> progress) {
        if(!new DriveInfo(Path.GetPathRoot(root)).DriveFormat.Equals("NTFS",StringComparison.OrdinalIgnoreCase)) {
            WriteLog("Disk compression skipped: destination is not NTFS.");return;
        }
        progress(96,"正在无损压缩安装目录，减少安装后的磁盘占用…");
        foreach(string arguments in new[]{"/C /S:\""+root+"\" /A /Q", "/C /EXE:LZX /F /S:\""+Path.Combine(root,"_internal")+"\" /A /Q"}) {
            var start=new ProcessStartInfo(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System),"compact.exe"),arguments) {
                WorkingDirectory=root,UseShellExecute=false,CreateNoWindow=true,
                RedirectStandardOutput=true,RedirectStandardError=true
            };
            using(var p=Process.Start(start)) {
                var output=p.StandardOutput.ReadToEndAsync();var error=p.StandardError.ReadToEndAsync();
                p.WaitForExit();WriteLog("Installed disk compression exit: "+p.ExitCode+"\n"+output.Result+error.Result);
            }
        }
    }
    static void VerifyInstalledGui(string root) {
        string report=Path.Combine(Path.GetTempPath(),"Suiyi-Workspace-"+Guid.NewGuid().ToString("N")+".json");
        try {
            var start=new ProcessStartInfo(Path.Combine(root,"Suiyi.exe"),"--self-test-workspace \""+report+"\"") {
                WorkingDirectory=root,UseShellExecute=false,CreateNoWindow=true,WindowStyle=ProcessWindowStyle.Hidden
            };
            using(var p=Process.Start(start)) {
                if(!p.WaitForExit(60000)) {p.Kill();throw new IOException("新版启动验证超时，旧版清理尚未执行。");}
                if(p.ExitCode!=0 || !File.Exists(report)) throw new IOException("新版启动验证失败，旧版清理尚未执行。");
            }
        } finally {if(File.Exists(report))File.Delete(report);}
    }
    static void RemoveSupersededProgramFiles(string root,string[] previous,HashSet<string> current) {
        foreach(string name in previous.Skip(1)) {
            // Optional installed models remain available across upgrades.
            if(current.Contains(name) || name.Replace('/','\\').StartsWith("models\\",StringComparison.OrdinalIgnoreCase)) continue;
            string path=SafePath(root,name);
            try {if(File.Exists(path)) File.Delete(path);}
            catch(Exception e) {WriteLog("Old program file retained: "+name+" "+e.Message);}
        }
        string manifest=Path.Combine(root,Marker);
        var remaining=File.ReadAllLines(manifest,Encoding.UTF8).Skip(1).Where(n=>File.Exists(SafePath(root,n)));
        File.WriteAllLines(manifest,(new[]{Identity}).Concat(remaining).ToArray(),Encoding.UTF8);
    }
    static void RemoveKnownOldInstallers() {
        // Only known, byte-verified Suiyi installers beside this installer; no directory sweep.
        var known=new Dictionary<string,string> {
            {"Suiyi-v0.2-Windows-x64-Setup.exe","080ad4fe65ec762e8a4cedb9c98714c0f541d239a4781dae281280ded1e90940"},
            {"Suiyi-v0.2-Compact-Setup.exe","fe9be8807d1a6a40120478f1fd1735fd9b6d876f9dd8d4396dd5354037080a8d"},
            {"Suiyi-v0.2.1-Core-Setup.exe","303d047dc05cc91ff093bb8b928c0c12df7c2763fb38e52fc1b712608c9a61c4"},
            {"Suiyi-v0.2.1-Core-Setup.zip","12a60ccff192fc372fa2d1ba3a6893b0231f2dc22e623fe24676409fb93331d4"},
            {"Suiyi-v0.3-Core-Setup.exe","c4f259b3e0e8638f2e4dc437df772190af75020c8ffbf2ab3ef22f37af48fc65"},
            {"Suiyi-v0.4.1-Update.exe","21fa52c733caa69476cbc501b6d05337a8888391f9eca742acd123ec4100eb3c"}
        };
        string folder=Path.GetDirectoryName(Application.ExecutablePath);
        foreach(var entry in known) {
            try {
                string path=SafePath(folder,entry.Key);
                if(!File.Exists(path) || path.Equals(Application.ExecutablePath,StringComparison.OrdinalIgnoreCase)) continue;
                string digest;
                using(var stream=File.OpenRead(path)) using(var sha=SHA256.Create()) digest=BitConverter.ToString(sha.ComputeHash(stream)).Replace("-","").ToLowerInvariant();
                if(digest!=entry.Value) {WriteLog("Unrecognized installer preserved: "+path);continue;}
                File.Delete(path);WriteLog("Removed superseded installer: "+path);
            } catch(Exception e) {WriteLog("Old installer retained: "+entry.Key+" "+e.Message);}
        }
    }
    public static void Install(string target,Action<int,string> progress,bool desktop,bool register=true) {
        string root=ValidateRoot(target);
        if(File.Exists(Path.Combine(root,Marker))) EnsureStopped(root);
        string marker=Path.Combine(root,Marker);
        string[] previous=File.Exists(marker)?File.ReadAllLines(marker,Encoding.UTF8):new[]{Identity};
        if(previous.Length<1 || previous[0]!=Identity) throw new IOException("已有安装清单无效。");
        var current=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        WriteLog("Install target: "+root);
        using(var input=File.OpenRead(Application.ExecutablePath)) {
#if COMPACT
            long length;byte[] expected;
            using(var info=System.Reflection.Assembly.GetExecutingAssembly().GetManifestResourceStream("PackageMetadata")) {
                var metadata=new BinaryReader(info);length=metadata.ReadInt64();expected=metadata.ReadBytes(32);
            }
            long offset=input.Length-length;
            if(length<=0 || offset<1024 || expected.Length!=32) throw new IOException("安装包不完整。");
#else
            if(input.Length<56) throw new IOException("安装包不完整。");
            input.Position=input.Length-56;
            var reader=new BinaryReader(input);
            long offset=reader.ReadInt64(),length=reader.ReadInt64();
            byte[] expected=reader.ReadBytes(32);
            if(Encoding.ASCII.GetString(reader.ReadBytes(8))!="SUIYI002" || offset<0 || length<=0 || offset+length!=input.Length-56) throw new IOException("安装包尾部校验失败。");
#endif
            progress(0,"正在验证安装包完整性…");
            using(var data=new SliceStream(input,offset,length)) {
                using(var hash=SHA256.Create()) {
                    if(!hash.ComputeHash(data).SequenceEqual(expected)) throw new IOException("安装包损坏，请重新复制完整文件。");
                }
                data.Position=0;
#if COMPACT
                ExtractCompact(root,progress);
                using(var reader=new StreamReader(System.Reflection.Assembly.GetExecutingAssembly().GetManifestResourceStream("FileMetadata"),Encoding.UTF8)) {
                    string line;while((line=reader.ReadLine())!=null) current.Add(line.Substring(line.IndexOf('\t')+1).Replace('/','\\'));
                }
#else
                using(var zip=new ZipArchive(data,ZipArchiveMode.Read,true)) {
                    long total=zip.Entries.Sum(e=>e.Length),done=0;
                    var drive=new DriveInfo(Path.GetPathRoot(root));
                    if(drive.AvailableFreeSpace<total+256L*1024*1024) throw new IOException("所选磁盘空间不足，需要约 "+(total/1e9).ToString("F1")+" GB 可用空间。");
                    var files=new List<string>();
                    foreach(var entry in zip.Entries) {
                        string name=entry.FullName;
                        if(name.EndsWith("/")) continue;
                        SafePath(root,name);files.Add(name.Replace('/','\\'));current.Add(name.Replace('/','\\'));
                    }
                    Directory.CreateDirectory(root);
                    // Explicit manifest makes partial installs removable without deleting unrelated files.
                    WriteInstallManifest(root,files);
                    byte[] buffer=new byte[1024*1024];
                    foreach(var entry in zip.Entries) {
                        if(entry.FullName.EndsWith("/")) continue;
                        string path=SafePath(root,entry.FullName);
                        Directory.CreateDirectory(Path.GetDirectoryName(path));
                        using(var source=entry.Open()) using(var dest=File.Create(path)) {
                            int n;
                            while((n=source.Read(buffer,0,buffer.Length))>0) {
                                dest.Write(buffer,0,n);done+=n;
                                progress((int)(done*95/total),"正在安装："+entry.FullName);
                            }
                        }
                    }
                }
#endif
            }
        }
        const string spaceNote="安装后空间与更新说明.txt";
        File.WriteAllText(SafePath(root,spaceNote),"本版会对 NTFS 安装目录自动进行无损压缩。\r\n请在文件夹属性中查看“占用空间”；“大小”仍显示解压后的逻辑总量。\r\nv0.5 包含分区界面、双主题、离线词典与原声回听；实际占用请查看安装目录属性，因磁盘与选装模型而异。\r\n模型文件与识别参数不变，首次加载可能受磁盘压缩影响。\r\n新版启动验证通过后，会清理安装清单中已被替代的旧程序文件，并删除本安装包旁已知且 SHA-256 匹配的旧版安装包。\r\n个人设置、选装模型、未列入清单的个人文件均保留；不会联网自动更新。\r\n",Encoding.UTF8);
        current.Add(spaceNote);WriteInstallManifest(root,new[]{spaceNote});
        CompressInstalledFiles(root,progress);
        if(!register) {WriteLog("Verified extraction complete: "+root);progress(100,"验证解压完成，未更改快捷方式或安装注册。");return;}
        progress(97,"正在验证新版启动…");
        VerifyInstalledGui(root);
        RemoveSupersededProgramFiles(root,previous,current);
        progress(97,"正在创建快捷方式和卸载入口…");
        string menu=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs),"随译");
        Directory.CreateDirectory(menu);
        Shortcut(Path.Combine(menu,"随译.lnk"),Path.Combine(root,"Suiyi.exe"),"");
        Shortcut(Path.Combine(menu,"卸载随译.lnk"),Path.Combine(root,"Uninstall.exe"),"/uninstall");
        if(desktop) Shortcut(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),"随译.lnk"),Path.Combine(root,"Suiyi.exe"),"");
        using(var key=Registry.CurrentUser.CreateSubKey(Key)) {
            key.SetValue("DisplayName","随译 v0.5 公开版（学习工作台）");key.SetValue("DisplayVersion","0.5-public.1");
            key.SetValue("InstallLocation",root);key.SetValue("DisplayIcon",Path.Combine(root,"Suiyi.exe"));
            key.SetValue("UninstallString","\""+Path.Combine(root,"Uninstall.exe")+"\" /uninstall");
            key.SetValue("NoModify",1,RegistryValueKind.DWord);key.SetValue("NoRepair",1,RegistryValueKind.DWord);
        }
        RemoveKnownOldInstallers();
        WriteLog("Install complete");progress(100,"安装完成，已清理可识别的旧版。可从开始菜单启动随译。");
    }
#if COMPACT
    static void ExtractCompact(string root,Action<int,string> progress) {
        var assembly=System.Reflection.Assembly.GetExecutingAssembly();
        var files=new Dictionary<string,long>(StringComparer.OrdinalIgnoreCase);
        using(var reader=new StreamReader(assembly.GetManifestResourceStream("FileMetadata"),Encoding.UTF8)) {
            string line;
            while((line=reader.ReadLine())!=null) {
                int tab=line.IndexOf('\t');
                if(tab<1) throw new IOException("无效的安装文件清单。");
                string name=line.Substring(tab+1);SafePath(root,name);
                files.Add(name,long.Parse(line.Substring(0,tab)));
            }
        }
        long total=files.Values.Sum();
        if(new DriveInfo(Path.GetPathRoot(root)).AvailableFreeSpace<total+256L*1024*1024) throw new IOException("安装约需 "+(total/1e9).ToString("F1")+" GB 可用空间。");
        Directory.CreateDirectory(root);
        WriteInstallManifest(root,files.Keys);
        string helperDir=Path.Combine(Path.GetTempPath(),"Suiyi-Decode-"+Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(helperDir);
        string helper=Path.Combine(helperDir,"7zr.exe");
        try {
            using(var source=assembly.GetManifestResourceStream("LocalDecoder")) using(var destination=File.Create(helper)) source.CopyTo(destination);
            var start=new ProcessStartInfo(helper,"x \""+Application.ExecutablePath+"\" -o\""+root+"\" -y -bb1 -bsp0 -sccUTF-8") {
                UseShellExecute=false,CreateNoWindow=true,WindowStyle=ProcessWindowStyle.Hidden,
                RedirectStandardOutput=true,RedirectStandardError=true,StandardOutputEncoding=Encoding.UTF8
            };
            progress(1,"正在无损解压模型和运行库…");
            using(var process=Process.Start(start)) {
                var error=process.StandardError.ReadToEndAsync();
                string line;long done=0;
                var seen=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                while((line=process.StandardOutput.ReadLine())!=null) {
                    if(line.StartsWith("- ")) {
                        string name=line.Substring(2).Replace('/','\\');
                        if(files.ContainsKey(name) && seen.Add(name)) {done+=files[name];progress((int)(done*95/total),"正在解压："+name);}
                    }
                }
                process.WaitForExit();
                if(process.ExitCode!=0) throw new IOException("解压失败（"+process.ExitCode+"）："+error.Result);
            }
            foreach(var file in files) {
                var actual=new FileInfo(SafePath(root,file.Key));
                if(!actual.Exists || actual.Length!=file.Value) throw new IOException("解压文件不完整："+file.Key);
            }
        } finally {
            try {File.Delete(helper);Directory.Delete(helperDir);} catch(IOException) {} catch(UnauthorizedAccessException) {}
        }
    }
#endif
    static void Shortcut(string path,string target,string args) {
        Type type=Type.GetTypeFromProgID("WScript.Shell");
        dynamic shell=Activator.CreateInstance(type);
        dynamic link=shell.CreateShortcut(path);
        link.TargetPath=target;link.WorkingDirectory=Path.GetDirectoryName(target);link.Arguments=args;
        link.IconLocation=target+",0";link.Save();
        System.Runtime.InteropServices.Marshal.FinalReleaseComObject(link);
        System.Runtime.InteropServices.Marshal.FinalReleaseComObject(shell);
    }
    static void DeleteShortcut(string path,string root) {
        if(!File.Exists(path)) return;
        dynamic shell=Activator.CreateInstance(Type.GetTypeFromProgID("WScript.Shell"));
        dynamic link=shell.CreateShortcut(path);
        string target=link.TargetPath;
        System.Runtime.InteropServices.Marshal.FinalReleaseComObject(link);
        System.Runtime.InteropServices.Marshal.FinalReleaseComObject(shell);
        if(target.StartsWith(root+"\\",StringComparison.OrdinalIgnoreCase)) File.Delete(path);
    }
    static void Remove(string directory,bool quiet) {
        string root=Path.GetFullPath(directory).TrimEnd('\\');
        EnsureStopped(root);
        string manifest=SafePath(root,Marker);
        var names=File.ReadAllLines(manifest,Encoding.UTF8);
        if(names.Length<2 || names[0]!=Identity) throw new IOException("未找到有效的随译安装清单，取消卸载。");
        var paths=names.Skip(1).Select(n=>SafePath(root,n)).ToArray();
        var folders=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach(string path in paths) {
            if(File.Exists(path)) File.Delete(path);
            string p=Path.GetDirectoryName(path);
            while(p!=null && p.StartsWith(root+"\\",StringComparison.OrdinalIgnoreCase)) { folders.Add(p);p=Path.GetDirectoryName(p); }
        }
        foreach(string folder in folders.OrderByDescending(p=>p.Length))
            if(Directory.Exists(folder) && !Directory.EnumerateFileSystemEntries(folder).Any()) Directory.Delete(folder);
        File.Delete(manifest);
        if(!Directory.EnumerateFileSystemEntries(root).Any()) Directory.Delete(root);
        string menu=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs),"随译");
        DeleteShortcut(Path.Combine(menu,"随译.lnk"),root);DeleteShortcut(Path.Combine(menu,"卸载随译.lnk"),root);
        DeleteShortcut(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),"随译.lnk"),root);
        if(Directory.Exists(menu) && !Directory.EnumerateFileSystemEntries(menu).Any()) Directory.Delete(menu);
        using(var key=Registry.CurrentUser.OpenSubKey(Key)) {
            if(key!=null && string.Equals(key.GetValue("InstallLocation") as string,root,StringComparison.OrdinalIgnoreCase)) {
                key.Close();Registry.CurrentUser.DeleteSubKey(Key,false);
            }
        }
        WriteLog("Uninstall complete: "+root);
        if(!quiet) MessageBox.Show("随译已卸载，个人偏好设置已保留。","随译");
    }
}

sealed class InstallForm : Form {
    TextBox location=new TextBox(); Button install=new Button(),browse=new Button();
    ProgressBar progress=new ProgressBar(); Label state=new Label();CheckBox desktop=new CheckBox(),agree=new CheckBox();Button terms=new Button();bool busy=false;
    public InstallForm() {
        Text="安装随译 v0.5 公开版";ClientSize=new Size(650,440);StartPosition=FormStartPosition.CenterScreen;
        FormBorderStyle=FormBorderStyle.FixedDialog;MaximizeBox=false;Font=new Font("Microsoft YaHei UI",10);
        var title=new Label{Text="随译 · v0.5 公开版",Font=new Font(Font.FontFamily,20),AutoSize=true,Location=new Point(25,22)};
        var info=new Label{Text="学习工作台 · 双主题 · 离线词典 · 原声循环回听\n安装后自动压缩磁盘占用，验证新版后清理旧版；turbo 选装。",AutoSize=true,Location=new Point(27,74)};
        location.SetBounds(27,145,495,30);location.Text=Setup.DefaultDir;
        browse.Text="浏览…";browse.SetBounds(535,143,86,33);browse.Click+=(s,e)=>{using(var dialog=new FolderBrowserDialog()){dialog.Description="选择独立的随译安装文件夹";if(dialog.ShowDialog()==DialogResult.OK)location.Text=Path.Combine(dialog.SelectedPath,"Suiyi");}};
        desktop.Text="创建桌面快捷方式";desktop.Checked=true;desktop.SetBounds(27,187,300,28);
        terms.Text="查看许可条款";terms.SetBounds(485,225,136,32);
        terms.Click+=(s,e)=>{using(var view=new Form{Text="随译许可与第三方条款",ClientSize=new Size(760,550),StartPosition=FormStartPosition.CenterParent}) {
            var text=new TextBox{Multiline=true,ReadOnly=true,ScrollBars=ScrollBars.Vertical,Dock=DockStyle.Fill,Font=new Font("Microsoft YaHei UI",10),Text=Setup.LicenseText()};
            view.Controls.Add(text);view.ShowDialog(this);
        }};
        agree.Text="我已阅读并同意许可（非商业使用免费）";agree.SetBounds(27,226,445,30);
        agree.CheckedChanged+=(s,e)=>{if(!busy)install.Enabled=agree.Checked;};
        progress.SetBounds(27,288,594,20);state.SetBounds(27,318,594,45);state.Text="安装不会开始采集，也不会修改游戏文件。";state.AutoEllipsis=true;
        install.Text="开始安装";install.SetBounds(485,382,136,36);install.Enabled=false;
        install.Click+=async(s,e)=>{
            if(install.Text=="打开随译") {Process.Start(Path.Combine(location.Text,"Suiyi.exe"));Close();return;}
            if(!agree.Checked)return;
            busy=true;install.Enabled=browse.Enabled=location.Enabled=desktop.Enabled=agree.Enabled=terms.Enabled=false;
            string path=location.Text;bool link=desktop.Checked;
            var updates=new Progress<KeyValuePair<int,string>>(p=>{progress.Value=p.Key;state.Text=p.Value;});
            int previous=-1;long tick=0;
            try {
                await Task.Run(()=>Setup.Install(path,(p,text)=>{long now=Environment.TickCount;if(p!=previous || now-tick>300){previous=p;tick=now;((IProgress<KeyValuePair<int,string>>)updates).Report(new KeyValuePair<int,string>(p,text));}},link));
                install.Text="打开随译";
            } catch(Exception ex) {state.Text="安装失败："+ex.Message;browse.Enabled=location.Enabled=desktop.Enabled=agree.Enabled=terms.Enabled=true;MessageBox.Show(ex.Message,"随译安装失败");}
            busy=false;install.Enabled=true;
        };
        FormClosing+=(s,e)=>{if(busy){e.Cancel=true;MessageBox.Show("正在安装，请等待完成。","随译");}};
        Controls.AddRange(new Control[]{title,info,location,browse,desktop,agree,terms,progress,state,install});
    }
}

sealed class SliceStream : Stream {
    Stream inner;long start,size,pos;
    public SliceStream(Stream stream,long offset,long length){inner=stream;start=offset;size=length;pos=0;}
    public override bool CanRead{get{return true;}}public override bool CanWrite{get{return false;}}public override bool CanSeek{get{return true;}}
    public override long Length{get{return size;}}public override long Position{get{return pos;}set{Seek(value,SeekOrigin.Begin);}}
    public override int Read(byte[] buffer,int offset,int count){inner.Position=start+pos;int n=inner.Read(buffer,offset,(int)Math.Min(count,size-pos));pos+=n;return n;}
    public override long Seek(long offset,SeekOrigin origin){long next=(origin==SeekOrigin.Begin?0:origin==SeekOrigin.Current?pos:size)+offset;if(next<0||next>size)throw new IOException("越界读取安装包");return pos=next;}
    public override void Flush(){} public override void SetLength(long value){throw new NotSupportedException();}public override void Write(byte[] b,int o,int c){throw new NotSupportedException();}
}
