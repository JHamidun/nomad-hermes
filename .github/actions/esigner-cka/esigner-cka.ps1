param(
  [Parameter(Mandatory = $true)]
  [ValidateSet('setup', 'sign', 'verify', 'teardown', 'dump-logs', 'teardown-cleanup')]
  [string]$Mode
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Mask-SecretValue {
  param([string]$Value)
  if (-not [string]::IsNullOrWhiteSpace($Value)) {
    Write-Output "::add-mask::$Value"
  }
}

function Resolve-CkaInstallDir {
  if (-not [string]::IsNullOrWhiteSpace($env:INPUT_CKA_INSTALL_DIR)) {
    return $env:INPUT_CKA_INSTALL_DIR
  }
  $candidates = @(
    'C:\Program Files (x86)\SSL Corp\SSL.COM eSigner CKA',
    'C:\Program Files\SSL Corp\SSL.COM eSigner CKA'
  )
  foreach ($candidate in $candidates) {
    if (Test-Path -LiteralPath $candidate) {
      return $candidate
    }
  }
  return $candidates[0]
}

function Resolve-CkaLogDir {
  if (-not [string]::IsNullOrWhiteSpace($env:INPUT_CKA_LOG_DIR)) {
    return $env:INPUT_CKA_LOG_DIR
  }
  if (-not [string]::IsNullOrWhiteSpace($env:RUNNER_TEMP)) {
    return (Join-Path $env:RUNNER_TEMP 'esigner-cka-logs')
  }
  return (Join-Path ([System.IO.Path]::GetTempPath()) 'esigner-cka-logs')
}

function Resolve-SignToolPath {
  if (-not [string]::IsNullOrWhiteSpace($env:ESIGNER_SIGNTOOL_PATH) -and (Test-Path -LiteralPath $env:ESIGNER_SIGNTOOL_PATH)) {
    return $env:ESIGNER_SIGNTOOL_PATH
  }

  $kitsRoots = @(
    'C:\Program Files (x86)\Windows Kits\10\bin',
    'C:\Program Files\Windows Kits\10\bin'
  )
  foreach ($root in $kitsRoots) {
    if (Test-Path -LiteralPath $root) {
      $found = Get-ChildItem -Path $root -Filter 'signtool.exe' -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match '\\x64\\signtool\.exe$' } |
        Sort-Object -Property FullName -Descending |
        Select-Object -First 1
      if ($null -ne $found) {
        return $found.FullName
      }
    }
  }

  $cmd = Get-Command 'signtool.exe' -ErrorAction SilentlyContinue
  if ($null -ne $cmd) {
    return $cmd.Source
  }
  throw 'Unable to locate signtool.exe in Windows SDK or PATH.'
}

function Resolve-TargetFiles {
  param(
    [string]$FilesInput,
    [string]$WorkDirInput
  )
  if ([string]::IsNullOrWhiteSpace($FilesInput)) {
    throw 'The "files" input must specify at least one file or glob pattern.'
  }

  $baseDir = if ([string]::IsNullOrWhiteSpace($WorkDirInput)) {
    (Get-Location).Path
  } elseif ([System.IO.Path]::IsPathRooted($WorkDirInput)) {
    $WorkDirInput
  } else {
    Join-Path (Get-Location).Path $WorkDirInput
  }

  if (-not (Test-Path -LiteralPath $baseDir)) {
    throw "Working directory does not exist: $baseDir"
  }

  $resolved = New-Object System.Collections.Generic.List[string]
  $lines = $FilesInput -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne '' -and -not $_.StartsWith('#') }

  foreach ($pattern in $lines) {
    $candidatePattern = if ([System.IO.Path]::IsPathRooted($pattern)) {
      $pattern
    } else {
      Join-Path $baseDir $pattern
    }

    if ($candidatePattern.Contains('*') -or $candidatePattern.Contains('?')) {
      $matches = @(Get-ChildItem -Path $candidatePattern -File -ErrorAction Stop)
      if ($matches.Count -eq 0) {
        throw "No files matched pattern: $pattern (resolved: $candidatePattern)"
      }
      foreach ($match in $matches) {
        if (-not $resolved.Contains($match.FullName)) {
          $resolved.Add($match.FullName)
        }
      }
    } else {
      if (-not (Test-Path -LiteralPath $candidatePattern -PathType Leaf)) {
        throw "Target file does not exist: $pattern (resolved: $candidatePattern)"
      }
      $fullPath = (Get-Item -LiteralPath $candidatePattern).FullName
      if (-not $resolved.Contains($fullPath)) {
        $resolved.Add($fullPath)
      }
    }
  }

  if ($resolved.Count -eq 0) {
    throw 'No target files resolved from "files" input.'
  }
  return $resolved.ToArray()
}

function Normalize-Thumbprint {
  param([string]$Thumbprint)
  if ([string]::IsNullOrWhiteSpace($Thumbprint)) {
    return ''
  }
  return (($Thumbprint -replace '[^0-9A-Fa-f]', '').ToUpperInvariant())
}

function Find-CodeSigningCert {
  param(
    [string]$ExpectedCn,
    [string]$ExpectedThumbprint
  )

  $normalizedExpectedThumb = Normalize-Thumbprint -Thumbprint $ExpectedThumbprint
  if (-not [string]::IsNullOrWhiteSpace($ExpectedThumbprint) -and $normalizedExpectedThumb.Length -ne 40) {
    throw "Invalid expected_thumbprint '$ExpectedThumbprint': must be 40 hexadecimal characters (SHA-1)."
  }

  $certs = @(Get-ChildItem -Path 'Cert:\CurrentUser\My' -ErrorAction Stop)
  if ($certs.Count -eq 0) {
    throw 'No certificates found in Cert:\CurrentUser\My.'
  }

  $now = Get-Date
  $matching = New-Object System.Collections.Generic.List[System.Security.Cryptography.X509Certificates.X509Certificate2]

  foreach ($cert in $certs) {
    $thumb = Normalize-Thumbprint -Thumbprint $cert.Thumbprint
    if (-not [string]::IsNullOrWhiteSpace($normalizedExpectedThumb)) {
      if ($thumb -ne $normalizedExpectedThumb) {
        continue
      }
    }

    if (-not [string]::IsNullOrWhiteSpace($ExpectedCn)) {
      if ($cert.Subject -notlike "*$ExpectedCn*") {
        continue
      }
    }

    if ($cert.NotAfter -le $now) {
      throw "Matched certificate $($cert.Thumbprint) ($($cert.Subject)) expired on $($cert.NotAfter.ToString('u'))."
    }
    if ($cert.NotBefore -gt $now) {
      throw "Matched certificate $($cert.Thumbprint) ($($cert.Subject)) is not valid until $($cert.NotBefore.ToString('u'))."
    }

    # Check Code Signing EKU (1.3.6.1.5.5.7.3.3) when EKU extension is present
    $ekuExt = $cert.Extensions | Where-Object { $_.Oid.Value -eq '2.5.29.37' } | Select-Object -First 1
    if ($null -ne $ekuExt) {
      $eku = [System.Security.Cryptography.X509Certificates.X509EnhancedKeyUsageExtension]$ekuExt
      $hasCodeSigning = $false
      foreach ($oid in $eku.EnhancedKeyUsages) {
        if ($oid.Value -eq '1.3.6.1.5.5.7.3.3') {
          $hasCodeSigning = $true
          break
        }
      }
      if (-not $hasCodeSigning) {
        continue
      }
    }

    $matching.Add($cert)
  }

  if ($matching.Count -eq 0) {
    $available = ($certs | ForEach-Object { "$($_.Thumbprint): $($_.Subject)" }) -join '; '
    throw "No valid code-signing certificate found in Cert:\CurrentUser\My matching CN='$ExpectedCn' thumbprint='$normalizedExpectedThumb'. Available: [$available]"
  }

  return ($matching | Sort-Object -Property NotAfter -Descending | Select-Object -First 1)
}

function Write-ActionOutputs {
  param(
    [string]$Thumbprint,
    [string]$Subject
  )
  if (-not [string]::IsNullOrWhiteSpace($env:GITHUB_OUTPUT)) {
    Add-Content -LiteralPath $env:GITHUB_OUTPUT -Value "thumbprint=$Thumbprint" -Encoding UTF8
    Add-Content -LiteralPath $env:GITHUB_OUTPUT -Value "subject=$Subject" -Encoding UTF8
  }
  if (-not [string]::IsNullOrWhiteSpace($env:GITHUB_ENV)) {
    Add-Content -LiteralPath $env:GITHUB_ENV -Value "ESIGNER_CERT_THUMBPRINT=$Thumbprint" -Encoding UTF8
  }
}

function Invoke-DumpCkaLogs {
  $logDir = Resolve-CkaLogDir
  $installDir = Resolve-CkaInstallDir
  $searchDirs = @($logDir, $installDir, (Join-Path $env:LOCALAPPDATA 'SSL Corp'), (Join-Path $env:APPDATA 'SSL Corp')) |
    Where-Object { -not [string]::IsNullOrWhiteSpace($_) -and (Test-Path -LiteralPath $_) } |
    Select-Object -Unique

  Write-Host '=== eSigner CKA Diagnostic Log Dump ==='
  if ($searchDirs.Count -eq 0) {
    Write-Host 'No CKA log directories found.'
    return
  }

  foreach ($dir in $searchDirs) {
    $logs = @(Get-ChildItem -Path $dir -Include '*.log', '*.txt' -Recurse -ErrorAction SilentlyContinue)
    foreach ($logFile in $logs) {
      Write-Host "--- Log file: $($logFile.FullName) ---"
      $content = Get-Content -LiteralPath $logFile.FullName -Tail 200 -ErrorAction SilentlyContinue
      foreach ($line in $content) {
        $sanitized = $line
        foreach ($secret in @($env:INPUT_PASSWORD, $env:INPUT_TOTP_SECRET, $env:INPUT_USERNAME)) {
          if (-not [string]::IsNullOrWhiteSpace($secret)) {
            $sanitized = $sanitized.Replace($secret, '***')
          }
        }
        Write-Host $sanitized
      }
    }
  }
}

function Invoke-SetupMode {
  Mask-SecretValue -Value $env:INPUT_USERNAME
  Mask-SecretValue -Value $env:INPUT_PASSWORD
  Mask-SecretValue -Value $env:INPUT_TOTP_SECRET
  Mask-SecretValue -Value $env:INPUT_CREDENTIAL_ID

  $missing = New-Object System.Collections.Generic.List[string]
  if ([string]::IsNullOrWhiteSpace($env:INPUT_USERNAME)) { $missing.Add('username (ESIGNER_USERNAME)') }
  if ([string]::IsNullOrWhiteSpace($env:INPUT_PASSWORD)) { $missing.Add('password (ESIGNER_PASSWORD)') }
  if ([string]::IsNullOrWhiteSpace($env:INPUT_TOTP_SECRET)) { $missing.Add('totp_secret (ESIGNER_TOTP_SECRET)') }
  if ($missing.Count -gt 0) {
    throw "Missing required SSL.com eSigner CKA credentials for setup: $($missing -join ', ')"
  }

  $logDir = Resolve-CkaLogDir
  New-Item -ItemType Directory -Path $logDir -Force | Out-Null

  $installDir = Resolve-CkaInstallDir
  $masterConfigExe = Join-Path $installDir 'masterconfig.exe'

  if (-not (Test-Path -LiteralPath $masterConfigExe)) {
    $zipUrl = $env:INPUT_CKA_ZIP_URL
    $expectedSha = ($env:INPUT_CKA_ZIP_SHA256).Trim().ToLowerInvariant()
    if ([string]::IsNullOrWhiteSpace($zipUrl) -or [string]::IsNullOrWhiteSpace($expectedSha)) {
      throw 'Both cka_zip_url and cka_zip_sha256 must be provided to download eSigner CKA.'
    }

    $downloadDir = Join-Path $logDir 'download'
    New-Item -ItemType Directory -Path $downloadDir -Force | Out-Null
    $zipPath = Join-Path $downloadDir 'SSL.COM-eSigner-CKA.zip'

    Write-Host "Downloading eSigner CKA from $zipUrl ..."
    $uriObj = $null
    if ([System.Uri]::TryCreate($zipUrl, [System.UriKind]::Absolute, [ref]$uriObj) -and $uriObj.IsFile) {
      Copy-Item -LiteralPath $uriObj.LocalPath -Destination $zipPath -Force
    } else {
      Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -UseBasicParsing
    }

    $actualSha = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualSha -ne $expectedSha) {
      Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
      throw "SHA-256 mismatch for eSigner CKA archive! Expected: $expectedSha, Actual: $actualSha"
    }
    Write-Host "Verified eSigner CKA SHA-256: $actualSha"

    $extractDir = Join-Path $downloadDir 'extracted'
    if (Test-Path -LiteralPath $extractDir) {
      Remove-Item -LiteralPath $extractDir -Recurse -Force
    }
    Expand-Archive -LiteralPath $zipPath -DestinationPath $extractDir -Force

    $installerExe = Get-ChildItem -Path $extractDir -Filter '*.exe' -Recurse | Select-Object -First 1
    if ($null -eq $installerExe) {
      throw "No installer executable found inside eSigner CKA archive at $extractDir"
    }

    Write-Host "Installing eSigner CKA silently via $($installerExe.Name) ..."
    $installLog = Join-Path $logDir 'cka-installer.log'
    $proc = Start-Process -FilePath $installerExe.FullName -ArgumentList @(
      '/CURRENTUSER',
      '/VERYSILENT',
      '/SUPPRESSMSGBOXES',
      '/NORESTART',
      "/DIR=`"$installDir`"",
      "/LOG=`"$installLog`""
    ) -Wait -PassThru -NoNewWindow

    if ($proc.ExitCode -ne 0) {
      throw "eSigner CKA installer exited with code $($proc.ExitCode)."
    }

    Remove-Item -LiteralPath $downloadDir -Recurse -Force -ErrorAction SilentlyContinue
  }

  $installDir = Resolve-CkaInstallDir
  $masterConfigExe = Join-Path $installDir 'masterconfig.exe'
  if (-not (Test-Path -LiteralPath $masterConfigExe)) {
    throw "masterconfig.exe not found at expected path: $masterConfigExe"
  }

  $configLog = Join-Path $logDir 'masterconfig-config.log'
  $configArgs = @(
    '-config',
    '-user', $env:INPUT_USERNAME,
    '-pass', $env:INPUT_PASSWORD,
    '-totp', $env:INPUT_TOTP_SECRET,
    '-key', '1',
    '-r'
  )
  if (-not [string]::IsNullOrWhiteSpace($env:INPUT_CREDENTIAL_ID)) {
    $configArgs += @('-cid', $env:INPUT_CREDENTIAL_ID)
  }

  Write-Host 'Configuring eSigner CKA and syncing certificate into Cert:\CurrentUser\My ...'
  $cfgOut = & $masterConfigExe @configArgs 2>&1
  $cfgExit = $LASTEXITCODE
  $cfgOut | Out-File -FilePath $configLog -Encoding UTF8
  if ($cfgExit -ne 0) {
    throw "masterconfig.exe -config failed with exit code $cfgExit"
  }

  $cert = Find-CodeSigningCert -ExpectedCn $env:INPUT_EXPECTED_CN -ExpectedThumbprint $env:INPUT_EXPECTED_THUMBPRINT
  Write-Host "Selected code-signing certificate: Thumbprint=$($cert.Thumbprint), Subject=$($cert.Subject), Expires=$($cert.NotAfter.ToString('u'))"
  Write-ActionOutputs -Thumbprint $cert.Thumbprint -Subject $cert.Subject
}

function Invoke-SignFileWithRetry {
  param(
    [string]$SignToolExe,
    [string]$Thumbprint,
    [string]$FilePath,
    [string]$PrimaryTsUrl,
    [string]$FallbackTsUrl
  )

  $tsServers = New-Object System.Collections.Generic.List[string]
  if (-not [string]::IsNullOrWhiteSpace($PrimaryTsUrl)) {
    $tsServers.Add($PrimaryTsUrl)
  }
  if (-not [string]::IsNullOrWhiteSpace($FallbackTsUrl) -and -not $tsServers.Contains($FallbackTsUrl)) {
    $tsServers.Add($FallbackTsUrl)
  }
  if ($tsServers.Count -eq 0) {
    $tsServers.Add('http://ts.ssl.com')
  }

  $maxAttemptsPerServer = 3
  $lastError = ''

  foreach ($tsUrl in $tsServers) {
    for ($attempt = 1; $attempt -le $maxAttemptsPerServer; $attempt++) {
      Write-Host "Signing '$FilePath' (thumbprint=$Thumbprint, timestamp=$tsUrl, attempt=$attempt/$maxAttemptsPerServer) ..."
      $signArgs = @(
        'sign',
        '/sha1', $Thumbprint,
        '/fd', 'sha256',
        '/tr', $tsUrl,
        '/td', 'sha256',
        '/v',
        $FilePath
      )

      $output = & $SignToolExe @signArgs 2>&1
      $exitCode = $LASTEXITCODE
      if ($exitCode -eq 0) {
        Write-Host "Successfully signed '$FilePath' via $tsUrl"
        return
      }

      $lastError = ($output | Out-String).Trim()
      Write-Warning "signtool failed on '$FilePath' via $tsUrl (attempt $attempt/$maxAttemptsPerServer, exit $exitCode): $lastError"
      if ($attempt -lt $maxAttemptsPerServer) {
        Start-Sleep -Seconds (2 * $attempt)
      }
    }
    Write-Warning "Exhausted retries on timestamp server $tsUrl for '$FilePath'; trying fallback if available."
  }

  throw "Failed to sign '$FilePath' after trying all timestamp servers. Last error: $lastError"
}

function Invoke-VerifySingleFile {
  param(
    [string]$SignToolExe,
    [string]$FilePath,
    [string]$ExpectedCn,
    [string]$ExpectedThumbprint
  )

  Write-Host "Verifying Authenticode signature on '$FilePath' ..."
  $verifyOut = & $SignToolExe 'verify' '/pa' '/v' $FilePath 2>&1
  $verifyExit = $LASTEXITCODE
  $allowSelfSigned = ($env:ESIGNER_TEST_SELF_SIGNED -eq '1')
  if ($verifyExit -ne 0) {
    $details = ($verifyOut | Out-String).Trim()
    if (-not ($allowSelfSigned -and ($details -match 'terminated in a root|not trusted by the trust provider|CERT_E_UNTRUSTEDROOT|0x800B0109') -and ($details -notmatch 'No signature found'))) {
      throw "signtool verify /pa /v failed for '$FilePath' (exit $verifyExit): $details"
    }
  }

  $authSig = Get-AuthenticodeSignature -LiteralPath $FilePath
  if ($null -eq $authSig) {
    throw "Get-AuthenticodeSignature returned null for '$FilePath'."
  }
  $allowedStatuses = if ($allowSelfSigned) { @('Valid', 'UnknownError') } else { @('Valid') }
  if ($authSig.Status -notin $allowedStatuses) {
    throw "Get-AuthenticodeSignature Status for '$FilePath' is '$($authSig.Status)' (expected 'Valid'). StatusMessage: $($authSig.StatusMessage)"
  }
  if ($null -eq $authSig.SignerCertificate) {
    throw "No SignerCertificate found on '$FilePath'."
  }

  $signerSubject = $authSig.SignerCertificate.Subject
  $signerThumb = Normalize-Thumbprint -Thumbprint $authSig.SignerCertificate.Thumbprint
  $normalizedExpectedThumb = Normalize-Thumbprint -Thumbprint $ExpectedThumbprint

  if (-not [string]::IsNullOrWhiteSpace($ExpectedCn) -and ($signerSubject -notlike "*$ExpectedCn*")) {
    throw "SignerCertificate Subject '$signerSubject' on '$FilePath' does not match expected CN '$ExpectedCn'."
  }
  if (-not [string]::IsNullOrWhiteSpace($normalizedExpectedThumb) -and ($signerThumb -ne $normalizedExpectedThumb)) {
    throw "SignerCertificate Thumbprint '$signerThumb' on '$FilePath' does not match expected thumbprint '$normalizedExpectedThumb'."
  }
  if ($null -eq $authSig.TimeStamperCertificate) {
    $verifyText = ($verifyOut | Out-String)
    if ($verifyText -notmatch 'Signature is timestamped' -and $verifyText -notmatch 'Timestamp Verified by') {
      throw "Missing RFC3161 counter-signature (TimeStamperCertificate) on '$FilePath'."
    }
  }

  Write-Host "Verified '$FilePath': Status=$($authSig.Status), Signer=$($signerSubject) [$signerThumb]"
}

function Invoke-SignMode {
  $cert = Find-CodeSigningCert -ExpectedCn $env:INPUT_EXPECTED_CN -ExpectedThumbprint $env:INPUT_EXPECTED_THUMBPRINT
  $signtool = Resolve-SignToolPath
  $files = Resolve-TargetFiles -FilesInput $env:INPUT_FILES -WorkDirInput $env:INPUT_WORK_DIR

  foreach ($file in $files) {
    Invoke-SignFileWithRetry `
      -SignToolExe $signtool `
      -Thumbprint $cert.Thumbprint `
      -FilePath $file `
      -PrimaryTsUrl $env:INPUT_TIMESTAMP_URL `
      -FallbackTsUrl $env:INPUT_FALLBACK_TIMESTAMP_URL

    Invoke-VerifySingleFile `
      -SignToolExe $signtool `
      -FilePath $file `
      -ExpectedCn $env:INPUT_EXPECTED_CN `
      -ExpectedThumbprint $cert.Thumbprint
  }

  Write-ActionOutputs -Thumbprint $cert.Thumbprint -Subject $cert.Subject
}

function Invoke-VerifyMode {
  $signtool = Resolve-SignToolPath
  $files = Resolve-TargetFiles -FilesInput $env:INPUT_FILES -WorkDirInput $env:INPUT_WORK_DIR
  $expectedThumb = if (-not [string]::IsNullOrWhiteSpace($env:INPUT_EXPECTED_THUMBPRINT)) {
    $env:INPUT_EXPECTED_THUMBPRINT
  } elseif (-not [string]::IsNullOrWhiteSpace($env:ESIGNER_CERT_THUMBPRINT)) {
    $env:ESIGNER_CERT_THUMBPRINT
  } else {
    ''
  }

  foreach ($file in $files) {
    Invoke-VerifySingleFile `
      -SignToolExe $signtool `
      -FilePath $file `
      -ExpectedCn $env:INPUT_EXPECTED_CN `
      -ExpectedThumbprint $expectedThumb
  }
}

function Invoke-TeardownCleanup {
  Write-Host 'Running eSigner CKA teardown and keystore cleanup ...'
  $installDir = Resolve-CkaInstallDir
  $masterConfigExe = Join-Path $installDir 'masterconfig.exe'
  if (Test-Path -LiteralPath $masterConfigExe) {
    try {
      & $masterConfigExe -Keep 0 2>&1 | Out-Null
    } catch {
      Write-Warning "masterconfig.exe -Keep 0 reported warning: $($_.Exception.Message)"
    }
  }

  $expectedCn = $env:INPUT_EXPECTED_CN
  $expectedThumb = Normalize-Thumbprint -Thumbprint $(if (-not [string]::IsNullOrWhiteSpace($env:INPUT_EXPECTED_THUMBPRINT)) { $env:INPUT_EXPECTED_THUMBPRINT } else { $env:ESIGNER_CERT_THUMBPRINT })

  $certs = @(Get-ChildItem -Path 'Cert:\CurrentUser\My' -ErrorAction SilentlyContinue)
  foreach ($cert in $certs) {
    $thumb = Normalize-Thumbprint -Thumbprint $cert.Thumbprint
    $shouldRemove = $false
    if (-not [string]::IsNullOrWhiteSpace($expectedThumb) -and ($thumb -eq $expectedThumb)) {
      $shouldRemove = $true
    } elseif (-not [string]::IsNullOrWhiteSpace($expectedCn) -and ($cert.Subject -like "*$expectedCn*")) {
      $shouldRemove = $true
    }

    if ($shouldRemove) {
      Write-Host "Removing code-signing certificate from Cert:\CurrentUser\My: $($cert.Thumbprint) ($($cert.Subject))"
      Remove-Item -LiteralPath $cert.PSPath -Force -ErrorAction SilentlyContinue
    }
  }

  foreach ($dir in @((Join-Path $env:LOCALAPPDATA 'SSL Corp'), (Join-Path $env:APPDATA 'SSL Corp'), (Resolve-CkaLogDir))) {
    if (-not [string]::IsNullOrWhiteSpace($dir) -and (Test-Path -LiteralPath $dir)) {
      Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction SilentlyContinue
    }
  }
  Write-Host 'eSigner CKA teardown completed.'
}

switch ($Mode) {
  'setup' { Invoke-SetupMode }
  'sign' { Invoke-SignMode }
  'verify' { Invoke-VerifyMode }
  'teardown' { Invoke-TeardownCleanup }
  'dump-logs' { Invoke-DumpCkaLogs }
  'teardown-cleanup' { Invoke-TeardownCleanup }
}
