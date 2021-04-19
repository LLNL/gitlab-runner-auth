Name:           gitlab-runner-auth
Version:        0.0.0
Release:        1%{?dist}
Summary:        Enables on-demand runner registration

License:        MIT
URL:            https://github.com/LLNL/gitlab-runner-auth
Source0:        https://github.com/LLNL/gitlab-runner-auth/archive/refs/tags/v%{version}.zip

Requires:       gitlab-runner

%description
This script is meant to be run as part of the ExecStartPre script in the systemd service file for Gitlab runners. The net effect is that restarting a runner will reconcile any authentication issues.

%prep
%setup -n %{name}-%{version}

%build
./package


%install
mkdir -p /etc/gitlab-runner
install -m 0700 register-runner /etc/gitlab-runner/register-runner


%files
%doc README.md



%changelog
