#!/usr/bin/env python3
import conans, copy, os, platform, shutil, subprocess, sys, tempfile, ue4cli
from os import path

def run(command, cwd=None, env=None):
	'''
	Executes a command and raises an exception if it fails
	'''
	proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd, env=env, universal_newlines=True)
	(stdout, stderr) = proc.communicate(input)
	if proc.returncode != 0:
		raise Exception(
			'child process {} failed with exit code {}'.format(command, proc.returncode) +
			'\nstdout: "{}"\nstderr: "{}"'.format(stdout, stderr)
		)


def detectClang():
	'''
	Detects the presence of clang and returns the version suffix (if any)
	'''
	
	# Check if clang is installed without any suffix
	if conans.tools.which("clang++") != None:
		return ""
	
	# Check if clang 3.8 or newer is installed with a version suffix
	for ver in reversed(range(38, 51)):
		suffix = "-{:.1f}".format(ver / 10.0)
		if conans.tools.which("clang++" + suffix) != None:
			return suffix
	
	raise Exception("could not detect clang. Please ensure clang 3.8 or newer is installed.")


def install(packageDir, profile):
	'''
	Installs a package
	'''
	run(["conan", "create", ".", "adamrehn/generated", "--profile", profile], cwd=packageDir)


def generate(libName, template, packageDir, profile):
	'''
	Generates and installs a wrapper package
	'''
	conanfile = template.replace("${LIBNAME}", libName)
	conans.tools.save(path.join(packageDir, "conanfile.py"), conanfile)
	install(packageDir, profile)


def main():
	
	# Determine the full path to the directories containing our files
	scriptDir = path.dirname(path.abspath(__file__))
	packagesDir = path.join(scriptDir, "packages")
	templateDir = path.join(scriptDir, "template")
	
	# Read the contents of the template conanfile for generated packages
	template = conans.tools.load(path.join(templateDir, "conanfile.py"))
	
	# Create a temporary directory to hold the generated conanfiles
	tempDir = tempfile.mkdtemp()
	
	# Use the Conan profile name "ue4" by default (to maintain clean separation from the default Conan profile)
	profile = "ue4"
	
	# Under Linux, make sure the ue4 Conan profile detects clang instead of GCC
	profileEnv = copy.deepcopy(os.environ)
	if platform.system() == "Linux":
		clangSuffix = detectClang()
		profileEnv["CC"] = "clang" + clangSuffix
		profileEnv["CXX"] = "clang++" + clangSuffix
	
	print("Removing the '{}' Conan profile if it already exists...".format(profile))
	profileFile = path.join(conans.paths.get_conan_user_home(), ".conan", "profiles", profile)
	if path.exists(profileFile):
		os.unlink(profileFile)
	
	print("Creating '{}' Conan profile using autodetected settings...".format(profile))
	run(["conan", "profile", "new", profile, "--detect"], env=profileEnv)
	
	# Under Linux, update the ue4 Conan profile to force the use of clang and libc++
	if platform.system() == "Linux":
		run(["conan", "profile", "update", "env.CC={}".format(profileEnv["CC"]), profile])
		run(["conan", "profile", "update", "env.CXX={}".format(profileEnv["CXX"]), profile])
		run(["conan", "profile", "update", "settings.compiler.libcxx=libc++", profile])
	
	print("Removing any previous versions of generated packages...")
	run(["conan", "remove", "--force", "*@adamrehn/generated"])
	
	print("Installing base packages...")
	install(path.join(packagesDir, "ue4lib"), profile)
	install(path.join(packagesDir, "libcxx"), profile)
	
	print("Retrieving thirdparty library list from ue4cli...")
	ue4 = ue4cli.UnrealManagerFactory.create()
	libs = [lib for lib in ue4.listThirdPartyLibs() if lib != 'libc++']
	
	# Generate the package for each UE4-bundled thirdparty library
	for lib in libs:
		print("Generating and installing wrapper package for {}...".format(lib))
		generate(lib, template, tempDir, profile)
	
	# Attempt to remove the temporary directory
	try:
		shutil.rmtree(tempDir)
	except:
		pass
	print("Done.")

if __name__ == "__main__":
	main()