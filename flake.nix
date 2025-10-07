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
      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = [
            python
            python.pkgs.pip
            python.pkgs.virtualenv
          ];
          shellHook = ''
            export PYTHONUNBUFFERED=1
            if [ ! -d .venv ]; then
              echo "Creating virtual environment..."
              python -m venv .venv
            fi
            source .venv/bin/activate
            if [ -f requirements.txt ] && [ ! -f .venv/installed ]; then
              echo "Installing requirements..."
              pip install -r requirements.txt
              touch .venv/installed
            fi
          '';
        };
      }
    );
}
