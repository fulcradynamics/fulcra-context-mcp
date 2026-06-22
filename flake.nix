{

  description = "Fulcra MCP Server";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs?ref=nixpkgs-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    flake-utils.inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        pythonVersion = pkgs.python314;
        pythonEnv = (
          pythonVersion.withPackages (
            p: with p; [
              uv
              pip
              wheel
              ruff
            ]
          )
        );
      in
      {

        devShells.default = pkgs.mkShell {
          packages = with pkgs; [
            pythonEnv
          ];
          shellHook = ''
            export PYTHONHOME=${pythonEnv}
            export UVPYTHONDOWNLOADS=never
            export UVPYTHONPREFERENCE=only-system
            export UV_PYTHON=${pythonEnv}
          '';
        };

      }
    );

}
