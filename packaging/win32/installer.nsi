# Greatly inspired by Deluge NSIS installer
# https://github.com/deluge-torrent/deluge/blob/develop/packaging/win32/Win32%20README.txt

!addplugindir nsis_plugins
!addincludedir nsis_plugins
!include "WordFunc.nsh"

# Script version; displayed when running the installer
!define GUARDATA_INSTALLER_VERSION "1.0"

# program information
!define PROGRAM_NAME "guardata"
!define PROGRAM_WEB_SITE "https://guardata.app"
!define APPGUID "631018D1-19CB-4B17-B249-154E6448D29A"

# Detect version from file
!define BUILD_DIR "build"
!searchparse /file ${BUILD_DIR}/BUILD.tmp `target = "` GUARDATA_FREEZE_BUILD_DIR `"`
!ifndef GUARDATA_FREEZE_BUILD_DIR
   !error "Cannot find freeze build directory"
!endif
!searchparse /file ${BUILD_DIR}/BUILD.tmp `guardata_version = "` PROGRAM_VERSION `"`
!ifndef PROGRAM_VERSION
   !error "Program Version Undefined"
!endif
!searchparse /file ${BUILD_DIR}/BUILD.tmp `platform = "` PROGRAM_PLATFORM `"`
!ifndef PROGRAM_PLATFORM
   !error "Program Platform Undefined"
!endif

# Python files generated
!define LICENSE_FILEPATH "${GUARDATA_FREEZE_BUILD_DIR}\LICENSE.txt"
!define INSTALLER_FILENAME "guardata-${PROGRAM_VERSION}-${PROGRAM_PLATFORM}-setup.exe"

!define WINFSP_INSTALLER "winfsp-1.7.20172.msi"

# Set default compressor
SetCompressor /FINAL /SOLID lzma
SetCompressorDictSize 64

# --- Interface settings ---
# Modern User Interface 2
!include MUI2.nsh
# Installer
!define MUI_ICON "guardata.ico"
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_RIGHT
!define MUI_HEADERIMAGE_BITMAP "installer-top.bmp"
!define MUI_WELCOMEFINISHPAGE_BITMAP "installer-side.bmp"
!define MUI_COMPONENTSPAGE_SMALLDESC
!define MUI_ABORTWARNING
# Start Menu Folder Page Configuration
!define MUI_STARTMENUPAGE_DEFAULTFOLDER ${PROGRAM_NAME}
!define MUI_STARTMENUPAGE_REGISTRY_ROOT "HKCR"
!define MUI_STARTMENUPAGE_REGISTRY_KEY "Software\${PROGRAM_NAME}"
!define MUI_STARTMENUPAGE_REGISTRY_VALUENAME "Start Menu Folder"
# Uninstaller
!define MUI_UNICON "${NSISDIR}\Contrib\Graphics\Icons\modern-uninstall.ico"
!define MUI_HEADERIMAGE_UNBITMAP "installer-top.bmp"
!define MUI_WELCOMEFINISHPAGE_UNBITMAP "installer-side.bmp"
!define MUI_UNFINISHPAGE_NOAUTOCLOSE
# Add shortcut
!define MUI_FINISHPAGE_SHOWREADME ""
!define MUI_FINISHPAGE_SHOWREADME_NOTCHECKED
!define MUI_FINISHPAGE_SHOWREADME_TEXT "Create Desktop Shortcut"
!define MUI_FINISHPAGE_SHOWREADME_FUNCTION CreateDesktopShortcut
# Run guardata after install, using explorer.exe to un-elevate priviledges
!define MUI_FINISHPAGE_RUN "$WINDIR\explorer.exe"
!define MUI_FINISHPAGE_RUN_PARAMETERS "$INSTDIR\guardata.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Run guardata"
!define MUI_FINISHPAGE_RUN_NOTCHECKED

# --- Start of Modern User Interface ---
Var StartMenuFolder

# Welcome, License
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE ${LICENSE_FILEPATH}

# Skipping the components page
# !insertmacro MUI_PAGE_COMPONENTS

# Let the user select the installation directory
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_STARTMENU Application $StartMenuFolder

# Run installation
!insertmacro MUI_PAGE_INSTFILES
# Popup Message if VC Redist missing
# Page Custom VCRedistMessage
# Display 'finished' page
!insertmacro MUI_PAGE_FINISH
# Uninstaller pages
!insertmacro MUI_UNPAGE_INSTFILES
# Language files
!insertmacro MUI_LANGUAGE "English"


# --- Functions ---

Function checkGuardataRunning
    check:
        System::Call 'kernel32::OpenMutex(i 0x100000, b 0, t "guardata") i .R0'
        IntCmp $R0 0 notRunning
            System::Call 'kernel32::CloseHandle(i $R0)'
            MessageBox MB_OKCANCEL|MB_ICONEXCLAMATION \
                "guardata is running, please close it first.$\n$\n \
                Click `OK` to retry or `Cancel` to cancel this upgrade." \
                /SD IDCANCEL IDOK check
            Abort
    notRunning:
FunctionEnd

# Check for running guardata instance.
Function .onInit

    UserInfo::GetAccountType
    pop $0
    ${If} $0 != "admin" ;Require admin rights on NT4+
        MessageBox mb_iconstop "Administrator rights are required for the installation."
        SetErrorLevel 740 ;ERROR_ELEVATION_REQUIRED
        Quit
    ${EndIf}

    Call checkGuardataRunning

    ReadRegStr $R0 HKLM \
    "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PROGRAM_NAME}" \
    "UninstallString"
    StrCmp $R0 "" done

    MessageBox MB_OKCANCEL|MB_ICONEXCLAMATION \
    "${PROGRAM_NAME} is already installed. $\n$\nClick `OK` to remove the \
    previous version or `Cancel` to cancel this upgrade." \
    /SD IDOK IDOK uninst
    Abort

    ;Run the uninstaller sequentially and silently
    ;https://nsis.sourceforge.io/Docs/Chapter3.html#installerusageuninstaller
    uninst:
      ClearErrors
      ExecWait '"$R0" /S _?=$INSTDIR'
    done:

FunctionEnd

Function un.onUninstSuccess
    HideWindow
    MessageBox MB_ICONINFORMATION|MB_OK "$(^Name) was successfully removed from your computer." /SD IDOK
FunctionEnd

Function un.onInit
    MessageBox MB_ICONQUESTION|MB_YESNO|MB_DEFBUTTON2 "Do you want to completely remove $(^Name)?" /SD IDYES IDYES +2
    Abort
FunctionEnd

Function CreateDesktopShortcut
    CreateShortCut "$DESKTOP\guardata.lnk" "$INSTDIR\guardata.exe"
FunctionEnd

# --- Installation sections ---
!define PROGRAM_UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PROGRAM_NAME}"
!define PROGRAM_UNINST_ROOT_KEY "HKLM"
!define PROGRAM_UNINST_FILENAME "$INSTDIR\guardata-uninst.exe"

BrandingText "${PROGRAM_NAME} Windows Installer v${GUARDATA_INSTALLER_VERSION}"
Name "${PROGRAM_NAME} ${PROGRAM_VERSION}"
OutFile "${BUILD_DIR}\${INSTALLER_FILENAME}"
InstallDir "$PROGRAMFILES64\guardata"

# No need for such details
ShowInstDetails hide
ShowUnInstDetails hide

; Check 64 bits
!include LogicLib.nsh
!include x64.nsh
Section
${IfNot} ${RunningX64}
	MessageBox mb_iconstop "Sorry, this requires a 64 bits Windows."
	SetErrorLevel 1637 ;ERROR_INSTALL_PLATFORM_UNSUPPORTED
	Quit
${EndIf}
SectionEnd

# Install main application
Section "guardata : trustless data cloud storage" Section1
    SectionIn RO
    !include "${BUILD_DIR}\install_files.nsh"

    SetOverwrite ifnewer
    SetOutPath "$INSTDIR"
    WriteIniStr "$INSTDIR\homepage.url" "InternetShortcut" "URL" "${PROGRAM_WEB_SITE}"

    !insertmacro MUI_STARTMENU_WRITE_BEGIN Application
        SetShellVarContext all
        CreateDirectory "$SMPROGRAMS\$StartMenuFolder"
        CreateShortCut "$SMPROGRAMS\$StartMenuFolder\guardata.lnk" "$INSTDIR\guardata.exe"
        CreateShortCut "$SMPROGRAMS\$StartMenuFolder\Website.lnk" "$INSTDIR\homepage.url"
        CreateShortCut "$SMPROGRAMS\$StartMenuFolder\Uninstall guardata.lnk" ${PROGRAM_UNINST_FILENAME}
        SetShellVarContext current
    !insertmacro MUI_STARTMENU_WRITE_END
SectionEnd

!macro InstallWinFSP
    SetOutPath "$TEMP"
    File ${WINFSP_INSTALLER}
    ; Use /qn to for silent installation
    ; Use a very high installation level to make sure it runs till the end
    ExecWait "msiexec /i ${WINFSP_INSTALLER} /qn INSTALLLEVEL=1000"
    Delete ${WINFSP_INSTALLER}
!macroend

# Install winfsp if necessary
Section "WinFSP" Section2
    ClearErrors
    ReadRegStr $0 HKCR "Installer\Dependencies\WinFsp" "Version"
    ${If} ${Errors}
      # WinFSP is not installed
      !insertmacro InstallWinFSP
    ${Else}
        ${VersionCompare} $0 "1.7.0" $R0
        ${VersionCompare} $0 "2.0.0" $R1
        ${If} $R0 == 2
            ${OrIf} $R1 == 1
                ${OrIf} $R1 == 0
                  # Incorrect WinSFP version (<1.7.0 or >=2.0.0)
                  !insertmacro InstallWinFSP
        ${EndIf}
    ${EndIf}
SectionEnd

# Create parsec:// uri association.
Section "Associate parsec:// URI links with guardata" Section3
    DeleteRegKey HKCR "parsec"
    WriteRegStr HKCR "parsec" "" "URL:parsec"
    WriteRegStr HKCR "parsec" "URL Protocol" ""
    WriteRegStr HKCR "parsec\shell\open\command" "" '"$INSTDIR\guardata.exe" "%1"'
SectionEnd

# Hidden: Remove obsolete entries
Section "-Remove obsolete entries" Section4
    # Remove obsolete guardata registry configuration
    DeleteRegKey HKCU "Software\Classes\CLSID\{${APPGUID}}"
    DeleteRegKey HKCU "Software\Classes\Wow6432Node\CLSID\{${APPGUID}}"
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Explorer\Desktop\NameSpace\{${APPGUID}}"
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Explorer\HideDesktopIcons\NewStartPanel\{${APPGUID}}"
    ClearErrors
SectionEnd

Section "Finish installation"
  # Fixes Windows broken size estimates
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKCU "${PROGRAM_UNINST_KEY}" "EstimatedSize" "$0"
SectionEnd

# Create uninstaller.
Section -Uninstaller
    WriteUninstaller ${PROGRAM_UNINST_FILENAME}
    WriteRegStr HKCU "${PROGRAM_UNINST_KEY}" "DisplayName" "$(^Name)"
    WriteRegStr HKCU "${PROGRAM_UNINST_KEY}" "UninstallString" "${PROGRAM_UNINST_FILENAME}"
    WriteRegStr HKCU "${PRODUCT_UNINST_KEY}" "DisplayVersion" "${PROGRAM_VERSION}"
    WriteRegStr HKCU "${PRODUCT_UNINST_KEY}" "Publisher" "BitLogiK"
    WriteRegStr HKCU "${PRODUCT_UNINST_KEY}" "DisplayIcon" "$INSTDIR\site-packages\parsec\core\resources\guardata.ico"
SectionEnd

# --- Uninstallation section ---
Section Uninstall
    # Delete guardata files.
    Delete "$INSTDIR\homepage.url"
    Delete ${PROGRAM_UNINST_FILENAME}
    !include "${BUILD_DIR}\uninstall_files.nsh"
    RmDir "$INSTDIR"

    # Delete Start Menu items.
    !insertmacro MUI_STARTMENU_GETFOLDER Application $StartMenuFolder
        SetShellVarContext all
        Delete "$SMPROGRAMS\$StartMenuFolder\guardata.lnk"
        Delete "$SMPROGRAMS\$StartMenuFolder\Uninstall guardata.lnk"
        Delete "$SMPROGRAMS\$StartMenuFolder\guardata Website.lnk"
        RmDir "$SMPROGRAMS\$StartMenuFolder"
        DeleteRegKey /ifempty HKCR "Software\guardata"
        SetShellVarContext current
    Delete "$DESKTOP\guardata.lnk"

    # Delete registry keys.
    DeleteRegKey ${PROGRAM_UNINST_ROOT_KEY} "${PROGRAM_UNINST_KEY}"
    # This key is only used by guardata, so we should always delete it
    DeleteRegKey HKCR "guardata"

  # Explorer shortcut keys potentially set by the application's settings
  DeleteRegKey HKCU "Software\Classes\CLSID\{${APPGUID}}"
  DeleteRegKey HKCU "Software\Classes\Wow6432Node\CLSID\{${APPGUID}"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Explorer\Desktop\NameSpace\{${APPGUID}"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Explorer\HideDesktopIcons\NewStartPanel\{${APPGUID}"

SectionEnd

# Add version info to installer properties.
VIProductVersion "${GUARDATA_INSTALLER_VERSION}.0.0"
VIAddVersionKey ProductName ${PROGRAM_NAME}
VIAddVersionKey Comments "guardata : trustless data cloud storage"
VIAddVersionKey CompanyName "BitLogiK"
VIAddVersionKey LegalCopyright "BitLogiK"
VIAddVersionKey FileDescription "${PROGRAM_NAME} Application Installer"
VIAddVersionKey FileVersion "${GUARDATA_INSTALLER_VERSION}.0.0"
VIAddVersionKey ProductVersion "${PROGRAM_VERSION}.0"
VIAddVersionKey OriginalFilename ${INSTALLER_FILENAME}

ManifestDPIAware true
