{
  description = "Jeeves IRC Butler";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python311;
        pythonEnv = python.withPackages (ps: with ps; [
          (ps.buildPythonPackage rec {
            pname = "irc";
            version = "20.4.0";
            src = ps.fetchPypi {
              inherit pname version;
              sha256 = "sha256-X9QS4VJ9KBd8vyEWP3XgAuRpFXqPvVhqXLvJXVVpNEI=";
            };
            propagatedBuildInputs = [ ps.jaraco-collections ps.jaraco-text ps.jaraco-functools ps.pytz ps.tempora ];
          })
          schedule
          requests
          pyyaml
          google-api-python-client
          beautifulsoup4
          timezonefinder
          pytz
          openai
          (ps.buildPythonPackage rec {
            pname = "deepl";
            version = "1.18.0";
            src = ps.fetchPypi {
              inherit pname version;
              sha256 = "sha256-kKz+6l3EbLFZ3pLqWX1rWqKFuLUJAzCqLqVJ0yMqBSo=";
            };
            propagatedBuildInputs = [ ps.requests ];
          })
        ]);
      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = [ pythonEnv ];
          shellHook = ''
            export PYTHONUNBUFFERED=1
          '';
        };
      }
    );
}
