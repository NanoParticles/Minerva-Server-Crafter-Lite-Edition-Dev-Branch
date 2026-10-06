import queue
import shutil
import time
import os
import sys
import threading
import requests
import sqlite3
from packaging.version import Version
import feedparser
import subprocess
import xmltodict
import json
from typing import Union,Tuple
from base.modules.config import MinecraftPropertiesSchema, rootFilepath, program_folder
from base.modules.utils import MCSCInternalError, CurseforgeClass, SoftwareSpec, TopographMapLogic
from base.modules.server import ServerFileIO
from base.modules.kernel import MCSCKernelCore
outputLog_updater = MCSCKernelCore(module="Updater")

class MCSCUpdater():
	'Version Updater for Minerva Server Crafter'
	q = queue.Queue()

	@classmethod
	def getUpdates(cls):
		try:
			PurpurLogic = cls.PurpurBaseClass()
			totalPurpurUpdates, purpurUpdateBool = PurpurLogic.updatePurpurTable() or (0, False)
			SpigotLogic = cls.SpigotBaseClass()
			totalBuildToolsUpdates, buildtoolUpdateBool = SpigotLogic.updateBuildToolsTable() or (0, False)
			ForgeLogic = cls.ForgeBaseClass()
			totalForgeUpdates, forgeUpdateBool = ForgeLogic.updateForgeVersionTable() or (0, False)
			VanillaMCLogic = cls.MinecraftVanillaBaseClass()
			totalMinecraftVanillaUpdates, minecraftVanillaUpdateBool = VanillaMCLogic.updateMinecraftVersions() or (0, False)
			FabricLogic = cls.FabricBaseClass()
			totalFabricInstallerUpdates, fabricInstallerUpdateBool = FabricLogic.updateFabricInstallerTable() or (0, False)
			totalFabricVersionUpdates, fabricVersionUpdateBool = FabricLogic.updateFabricVersions() or (0, False)
			versionUpdateDefinitions = int(totalPurpurUpdates) + int(totalBuildToolsUpdates) + int(totalForgeUpdates) + int(totalMinecraftVanillaUpdates) + int(totalFabricInstallerUpdates) + int(totalFabricVersionUpdates)
			if versionUpdateDefinitions > 0:
				#What was updated?
				updateList = []
				if purpurUpdateBool == True:
					updateList.append("Purpur Build(s)")
				if buildtoolUpdateBool == True:
					updateList.append("BuildTools Version(s)")
				if forgeUpdateBool == True:
					updateList.append("Forge Version(s)")
				if minecraftVanillaUpdateBool == True:
					updateList.append("Minecraft Vanilla Version(s)")
				if fabricInstallerUpdateBool == True:
					updateList.append("Fabric Installer Version(s)")
				if fabricVersionUpdateBool == True:
					updateList.append("Fabric Version(s)")
				totalUpdates = len(updateList)
				#We generated the list. Notify the user
				outputLog_updater.info_print(f"There was {totalUpdates} update(s) made to table(s). Total number of changes: {versionUpdateDefinitions}. Rebooting...")
				if minecraftVanillaUpdateBool == True:
					outputLog_updater.info_print("Vanilla Update detected. Halting Reboot and Generating Schema...")
					postUpdate_schemaGen = MinecraftPropertiesSchema()
					postUpdate_schemaGenVersion = str(cls.MinecraftVanillaBaseClass.getLatest())
					postUpdate_schemaGen.serverPropertiesToSchema(minecraft_version=postUpdate_schemaGenVersion,include_defaults=True)
					#Moving Schema to the latest config
					shutil.move(str(rootFilepath) + f"/base/assets/config/versions/{postUpdate_schemaGenVersion}/schema.json",str(rootFilepath) + "/base/assets/config/versions/latest/schema.json")
					time.sleep(2.0)
					outputLog_updater.info_print("Schema Generated. Rebooting...")
				os.execl(sys.executable,sys.executable,*sys.argv)
			else:
				outputLog_updater.info_print("No updates detected.")
				return

		except MCSCInternalError as e:
			outputLog_updater.error_print(f"Internal Error has occured: {e}")
			return

	class VersionCacheObject():
		def __init__(self):
			raise RuntimeError("Direct calling detected. Avoid doing this.")

		class onVersion():
			def __init__(self):
				raise RuntimeError("Direct calling detected. Avoid doing this.")
			
			@staticmethod
			def generateListPopulation(versionList: list | None = None) -> list:
				if not isinstance(versionList, list):
					return []
				result = []
				for version in versionList:
					version_check = MCSCUpdater.VersionCacheObject.onVersion.lookupVersion(version=str(version))
					if isinstance(version_check, bool) and version_check:
						result.append(version)
				return result

			@staticmethod
			def lookupVersion(version: str | None = None) -> Union[bool,Tuple[bool,str]]:
				'Looks up if version is in the cache and in the database. Returns True if they are in both in the cache and in the database table. Otherwise, returns False if and only if they are not in either the database table or the cache. However, if its missing while its present somewhere else, it returns as a tuple with False, and where it failed'
				if not isinstance(version, str):
					return False
				with open(str(rootFilepath) + "/properties.json","r") as jsonObject:
					data_dump = json.load(jsonObject)
				currentCache = data_dump["version_cache"]
				listingPopulation = currentCache["listing"]
				with SoftwareSpec.changeDir(path=str(rootFilepath)):
					MCSCDatabase = sqlite3.connect("mcsc_data.db")
					MCSC_Cursor = MCSCDatabase.cursor()
					MCSC_Cursor.execute("SELECT version FROM minecraftversion_Table")
					dbVersions = [v[0] for v in MCSC_Cursor.fetchall()]
					MCSC_Cursor.close()
					MCSCDatabase.close()
				cacheLookUp = version in listingPopulation
				dbLookUp = version in dbVersions
				if cacheLookUp and dbLookUp:
					return True
				if not cacheLookUp and not dbLookUp:
					return False
				return (False, "cache" if not cacheLookUp else "database")

			@staticmethod
			def addToCache(version: str | None = None):
				'Adds version to cache as a known good version'
				if not isinstance(version, str):
					return
				with open(str(rootFilepath) + "/properties.json","r") as jsonFile_:
					data_obj = json.load(jsonFile_)
				cache = data_obj['version_cache']
				version_listing = cache['listing']
				newVersionListing = []
				if version not in version_listing:
					newVersionListing.append(version)
					for item in version_listing:
						newVersionListing.append(item)
					data_obj['version_cache']['listing'] = newVersionListing
				with open(str(rootFilepath) + "/properties.json","w") as newJsonFile:
					json.dump(data_obj,newJsonFile,indent=4)
				return

			@staticmethod
			def addVersionCacheEntriesToTables():
				'Adds the cached database entries from cache to the table data'
				with open(str(rootFilepath) + "/properties.json","r") as data_json:
					json_dataobj = json.load(data_json)
					cache_OBJ = json_dataobj['version_cache']
					dbEntries = cache_OBJ['db_entries']
					with SoftwareSpec.changeDir(path=str(rootFilepath)):
						MCSCDatabase = sqlite3.connect("mcsc_data.db")
						MCSC_Cursor = MCSCDatabase.cursor()
						MCSC_Cursor.execute("PRAGMA table_info(minecraftversion_Table)")
						existing_columns = {str(row[1]) for row in MCSC_Cursor.fetchall()}
						if "java-version" not in existing_columns:
							MCSC_Cursor.execute('ALTER TABLE minecraftversion_Table ADD COLUMN "java-version" TEXT DEFAULT "8"')
							MCSCDatabase.commit()
						MCSC_Cursor.execute('DELETE FROM minecraftversion_Table')
						MCSCDatabase.commit()
					MCSC_Cursor.execute("VACUUM;")
					MCSCDatabase.commit()
					for item in dbEntries:
						java_version = item.get('java-version', item.get('javaVersion', 8))
						MCSC_Cursor.execute(
							'INSERT INTO minecraftversion_Table (version, timestampRelease, `java-version`) VALUES (?, ?, ?)',
							(str(item['version']), str(item['timestamp']), str(java_version))
						)
					MCSCDatabase.commit()
					MCSC_Cursor.close()
					MCSCDatabase.close()
				return

	@classmethod
	def updater(cls):
		try:
			cls.getUpdates()
			cls.q.put(True)
		except MCSCInternalError as e:
			outputLog_updater.error_print(e)
			cls.q.put(False)

	@classmethod
	def runUpdates(cls):
		#Thread the updates
		updaterThread = threading.Thread(target=cls.updater,name="Minerva Server Crafter - Updater",daemon=True)
		updaterThread.start()
		threadresult = cls.q.get()
		if threadresult == True:
			updaterThread.join()
			outputLog_updater.info_print("Database Table Updates completed.")
			ServerFileIO.onBoot_firstLoadCheck()
			outputLog_updater.info_print("Launching...")
			return
		else:
			raise MCSCInternalError("Failed to run Updates. Internal Exception")

	class MinecraftVanillaBaseClass():
		'Utility for handling Minecaft Vanilla Updates'
		def __init__(self):
			self.outputLog_vanillaupdates = MCSCKernelCore(module="Updater",logic="Vanilla Updates")
			return

		def rebuildCache(self):
			'Rebuilds the version cache'
			self.outputLog_vanillaupdates.info_print("Rebuilding Cache...")
			with open(str(rootFilepath) + "/properties.json","r") as jsonCache:
				dataDump = json.load(jsonCache)
			new_cache = []
			versionswithServer = []
			versionmanifestResponse = requests.get(url="https://piston-meta.mojang.com/mc/game/version_manifest_v2.json", timeout=30)
			if versionmanifestResponse.status_code == 200:
				manifestData = versionmanifestResponse.json()
				versionlisting = manifestData['versions']
				versionDict = {v['id']: v['url'] for v in versionlisting}
				session = requests.Session()
				java_version_map = {}

				for item, versionURL in versionDict.items():
					try:
						versionResponse = session.get(url=str(versionURL), timeout=15)
					except (Exception, MCSCInternalError):
						continue
					if versionResponse.status_code != 200:
						continue
					versiondata = versionResponse.json()
					versionDownloadSection = versiondata.get('downloads', {})
					if "server" in versionDownloadSection:
						self.outputLog_vanillaupdates.info_print(f"Found version {item} with a server.jar. Adding to good version listing...")
						versionswithServer.append(item)
						javaVersionObj = versiondata.get("javaVersion", {})
						java_version_map[item] = javaVersionObj.get("majorVersion") or 8

				for version_ in versionlisting:
					versionID = version_['id']
					timestamp = version_['releaseTime']
					if versionID in versionswithServer:
						new_cache.append({
							'version': str(versionID),
							'timestamp': str(timestamp),
							'java-version': str(java_version_map.get(versionID, 8))
						})

				version_cache = dataDump.setdefault('version_cache', {})
				version_cache['listing'] = versionswithServer
				version_cache['db_entries'] = new_cache
				with open(str(rootFilepath) + "/properties.json","w") as _jsonUpdate:
					json.dump(dataDump,_jsonUpdate,indent=4)
			return
		
		@staticmethod
		def getLatest():
			'Returns the id of the first entry in version manifest'
			response = requests.get(url="https://piston-meta.mojang.com/mc/game/version_manifest_v2.json", timeout=30)
			if response.status_code == 200:
				datadump = response.json()
				return datadump['versions'][0]['id']
			return None

		def omitedVersions(self):
			'Returns a list of versions that does not have server.jar. This is best for historical versions that do not have server jars(Cave game, infdev , alpha , and beta)'
			with SoftwareSpec.changeDir(path=str(rootFilepath)):
				MCSCDatabase = sqlite3.connect('mcsc_data.db')
				MCSC_Cursor = MCSCDatabase.cursor()
				MCSC_Cursor.execute("SELECT * FROM minecraftVersionBlacklist")
				blacklist = [str(row[0]) for row in MCSC_Cursor.fetchall()]
				MCSC_Cursor.close()
				MCSCDatabase.close()
			return blacklist
		
		def validServerVersions(self, versionList: list | None = None):
			'Returns a list of versions that does have a server jar distribution. This is best for earlier versions after beta'
			if not isinstance(versionList, list):
				return []
			self.outputLog_vanillaupdates.info_print("Compiling server version list...")
			versionswithServer = MCSCUpdater.VersionCacheObject.onVersion.generateListPopulation(versionList=versionList)
			self.outputLog_vanillaupdates.info_print(versionswithServer)
			result = []
			for item_ in versionList:
				versionResult = item_['version']
				if versionResult in versionswithServer:
					self.outputLog_vanillaupdates.info_print(f"Found version {versionResult} in the known good list of version. Allowing...")
					result.append(item_)
				else:
					self.outputLog_vanillaupdates.info_print(f"Version {versionResult} is a bad version. Disallowing...")
			self.outputLog_vanillaupdates.info_print("Done processing version list.")
			return result

		def updateMinecraftVersions(self):
			'Checks for Minecraft Version updates. When there is an update, it gets added to the table, and Minerva Server Crafter reboots'
			result = (0, False)
			versionManifestURL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
			response = requests.get(versionManifestURL, timeout=30)

			if response.status_code != 200:
				outputLog_updater.info_print("Failed to get version manifest")
				return result

			manifestData = response.json()
			versionswithTime = [{'version': version['id'], 'timestamp': version['releaseTime']} for version in manifestData['versions']]
			sortedVersions = sorted(versionswithTime, key=lambda x: x['timestamp'], reverse=True)
			with SoftwareSpec.changeDir(path=str(rootFilepath)):
				MCSCDatabase = sqlite3.connect("mcsc_data.db")
				MCSC_Cursor = MCSCDatabase.cursor()
				MCSC_Cursor.execute('SELECT version FROM minecraftversion_Table')
				existing_versions = {str(row[0]) for row in MCSC_Cursor.fetchall()}
				MCSC_Cursor.close()
				MCSCDatabase.close()

			versionBlackList = set(self.omitedVersions())
			detected_new_versions = [
				version for version in sortedVersions
				if version['version'] not in existing_versions and version['version'] not in versionBlackList
			]
			totalupdates = len(detected_new_versions)
			if not detected_new_versions:
				self.outputLog_vanillaupdates.info_print("No new Vanilla Minecraft Versions detected")
				return result

			self.outputLog_vanillaupdates.info_print(f"There are {totalupdates} new Minecraft Version(s) updates. Updating...")
			with open(str(rootFilepath) + "/properties.json","r") as jsonFile:
				dataDump = json.load(jsonFile)
			cacheObject = dataDump.setdefault('version_cache', {})
			cache_listing = cacheObject.get('listing', [])
			cache_db_entries = cacheObject.get('db_entries', [])
			cache_listing_set = set(str(item) for item in cache_listing)
			cache_db_entry_set = set(str(item.get('version')) for item in cache_db_entries if isinstance(item, dict))
			versionUrlMap = {v['id']: v['url'] for v in manifestData['versions']}
			new_listing_entries = []
			new_db_entries = []
			session = requests.Session()

			for item in detected_new_versions:
				version_id = str(item['version'])
				version_url = versionUrlMap.get(version_id)
				if not version_url:
					continue
				try:
					versionResponse = session.get(url=str(version_url), timeout=15)
				except (Exception, MCSCInternalError):
					continue
				if versionResponse.status_code != 200:
					continue
				versiondata = versionResponse.json()
				if "server" not in versiondata.get('downloads', {}):
					continue
				javaVersionObj = versiondata.get("javaVersion", {})
				jreVersion = javaVersionObj.get("majorVersion") or 8
				self.outputLog_vanillaupdates.info_print(
					f"Found version {version_id} with a server.jar. Adding to good version listing..."
				)
				if version_id not in cache_listing_set:
					new_listing_entries.append(version_id)
					cache_listing_set.add(version_id)
				if version_id not in cache_db_entry_set:
					new_db_entries.append({
						'version': str(version_id),
						'timestamp': str(item['timestamp']),
						'java-version': str(jreVersion),
					})
					cache_db_entry_set.add(version_id)

			actual_inserts = len(new_db_entries)
			self.outputLog_vanillaupdates.info_print(
				f"Version update summary: detected={totalupdates}, inserted={actual_inserts}"
			)
			if not new_listing_entries and not new_db_entries:
				self.outputLog_vanillaupdates.info_print("No new Vanilla Minecraft Versions detected")
				return (0, False)

			dataDump['version_cache']['listing'] = new_listing_entries + cache_listing
			dataDump['version_cache']['db_entries'] = new_db_entries + cache_db_entries
			with open(str(rootFilepath) + "/properties.json","w") as _jsonUpdate:
				json.dump(dataDump,_jsonUpdate,indent=4)
			MCSCUpdater.VersionCacheObject.onVersion.addVersionCacheEntriesToTables()
			self.outputLog_vanillaupdates.info_print('Version Table has been updated successfully.')
			return (int(actual_inserts), True)

	class PurpurBaseClass():
			'Utility that handles the compatibilities for Purpur'

			def __init__(self):
				self.outputLog_purpurupdates = MCSCKernelCore(module="Updater",logic="Purpur Updates")
				return

			@staticmethod
			def getCompatibleVersions() -> list:
				#Parse the JSON
				response = requests.get("https://api.purpurmc.org/v2/purpur")
				if response.status_code == 200:
					purpurRawData = response.json()
					compatibleVersions = [s for s in purpurRawData["versions"]]
					return compatibleVersions
				return []

			def updatePurpurTable(self):
				'Checks for updates from the Purpur API. When there is a new build is found, the table gets updated(Newest to oldest). When the purpur table is updated, Minerva Server Crafter reboots'
				result = (0,False)
				baseurl = "https://api.purpurmc.org/v2/purpur/"
				response = requests.get(baseurl)
				if response.status_code == 200:
					rawpurpur = response.json()
					currentversionData = [str(Version(v)) for v in rawpurpur["versions"]]
					currentBuilds = {}
					for version in currentversionData:
						buildURL = f"{baseurl}{version}"
						mcVersion = Version(version)
						buildresponse = requests.get(buildURL)
						if buildresponse.status_code == 200:
							rawbuildData = buildresponse.json()
							currentbuilds = rawbuildData["builds"]["all"]
							buildDataIntegrityCheck = [int(i) for i in currentbuilds]
							sortedBuilds = sorted(buildDataIntegrityCheck,reverse=True)
							currentBuilds[str(mcVersion)] = sortedBuilds
					sortedCurrentBuilds = sorted(currentBuilds.items(),reverse=True)
					currentBuilds = dict(sortedCurrentBuilds)
					with SoftwareSpec.changeDir(path=str(rootFilepath)):
						MCSCDatabase = sqlite3.connect("mcsc_data.db")
						MCSC_Cursor = MCSCDatabase.cursor()
						MCSC_Cursor.execute("SELECT Build_ID, Minecraft_Version FROM PurpurVersion_Table")
						existingBuilds = set((int(row[0]), str(row[1])) for row in MCSC_Cursor.fetchall())
						newBuilds = []
						for mcversion, buildList in currentBuilds.items():
							for build in buildList:
								buildPair = (int(build), str(mcversion))
								if buildPair not in existingBuilds:
									newBuilds.append(buildPair)

						totalNewBuilds = len(newBuilds)
						if newBuilds:
							MCSC_Cursor.execute("DELETE FROM PurpurVersion_Table")
							MCSCDatabase.commit()
							MCSC_Cursor.execute("VACUUM;")
							MCSCDatabase.commit()
							self.outputLog_purpurupdates.info_print(f"There are {totalNewBuilds} new build(s). Updating Table...")
							for mcversion,purpurBuildList in currentBuilds.items():
								for purpurBuildID in purpurBuildList:
									MCSC_Cursor.execute("INSERT INTO PurpurVersion_Table VALUES (?,?)", (purpurBuildID,mcversion))
							MCSCDatabase.commit()
							MCSC_Cursor.close()
							MCSCDatabase.close()
							result = tuple((int(totalNewBuilds),True))
							self.outputLog_purpurupdates.info_print("Build Table has been updated successfully.")
							return result

						self.outputLog_purpurupdates.info_print("No new Purpur builds detected")
						MCSC_Cursor.close()
						MCSCDatabase.close()
				return result
						
			@staticmethod
			def getBuildsbyVersion(version) -> list:
				'Returns a list of Purpur Versions thats compatiable with the given Minecraft Version'
				with SoftwareSpec.changeDir(path=str(rootFilepath)):
					MCSCDatabase = sqlite3.connect("mcsc_data.db")
					MCSC_Cursor = MCSCDatabase.cursor()
					MCSC_Cursor.execute("SELECT Build_ID FROM PurpurVersion_Table WHERE Minecraft_Version = ?", (str(version),))
					builds = [row[0] for row in MCSC_Cursor.fetchall()]
					MCSC_Cursor.close()
					MCSCDatabase.close()
					return builds

	class SpigotBaseClass():
			'Utility that handles the compatiblities thats tied to Spigot and its forks'

			def __init__(self):
				self.outputLog_spigot = MCSCKernelCore(module="Updater",logic="BuildTools Updates")
				return

			@staticmethod
			def getVersionListing() -> list:
				'Returns a list of minecraft versions tailored to spigot/craftbukkit'
				url = "https://hub.spigotmc.org/nexus/repository/snapshots/org/spigotmc/spigot-api/maven-metadata.xml"
				response = requests.get(url=str(url))
				if response.status_code == 200:
					data = xmltodict.parse(response.content)
					versions = data['metadata']['versioning']['versions']
					currentVersions = [str(v) for v in versions['version']]
					versionListing = []
					for item in currentVersions:
						mcversion = item.split("-")[0]
						if mcversion not in versionListing:
							versionListing.append(mcversion)
					return versionListing
				return []

			def updateBuildToolsTable(self):
				'Checks for successful builds of BuildTools in the jenkins repository. Failed builds are exempt from the result. When there is successful builds thats not in the database table, the table gets updated(newest builds to oldest). When the table gets updated, Minerva Server Crafter reboots.'
				result = (0,False)
				response = requests.get("https://hub.spigotmc.org/jenkins/job/BuildTools/api/json")
				if response.status_code == 200:
					buildtoolsjson = response.json()
					availableBuilds = [i for i in buildtoolsjson['builds']]
					successfulBuilds = {}
					for item in availableBuilds:
						key = item.get('number')
						value = item.get('url')
						successfulBuilds[key] = value

					rssfeed_failedBuilds = feedparser.parse("https://hub.spigotmc.org/jenkins/job/BuildTools/rssFailed")
					failedBuilds = {entry.get('title'): entry.get('link') for entry in rssfeed_failedBuilds['entries']}
					keys_to_delete = []
					for build_id, build_url in successfulBuilds.items():
						if build_url in failedBuilds.values():
							keys_to_delete.append(build_id)
					for key in keys_to_delete:
						del successfulBuilds[key]

					with SoftwareSpec.changeDir(path=str(rootFilepath)):
						MCSCDatabase = sqlite3.connect("mcsc_data.db")
						MCSC_Cursor = MCSCDatabase.cursor()
						MCSC_Cursor.execute("SELECT BuildID, Url FROM BuildTools_SuccessfulBuildVerified_Table")
						databaseData = {row[0]:row[1] for row in MCSC_Cursor.fetchall()}
						missingEntries = {a: b for a, b in successfulBuilds.items() if a not in databaseData}
						totalEntriesMissing = len(missingEntries)
						if missingEntries:
							MCSC_Cursor.execute("DELETE FROM BuildTools_SuccessfulBuildVerified_Table")
							MCSCDatabase.commit()
							MCSC_Cursor.execute("VACUUM;")
							MCSCDatabase.commit()
							self.outputLog_spigot.info_print(f"There are {totalEntriesMissing} new successful build(s). Updating Table...")
							for build_id, url in missingEntries.items():
								MCSC_Cursor.execute("INSERT INTO BuildTools_SuccessfulBuildVerified_Table (BuildID, Url) VALUES (?,?)", (build_id, url))
							for build_id, url in databaseData.items():
								MCSC_Cursor.execute("INSERT INTO BuildTools_SuccessfulBuildVerified_Table (BuildID, Url) VALUES (?,?)", (build_id, str(url)))
							MCSCDatabase.commit()
							MCSC_Cursor.close()
							MCSCDatabase.close()
							result = tuple((int(totalEntriesMissing), True))
							self.outputLog_spigot.info_print("Build Table has been updated successfully.")
							return result
						MCSC_Cursor.close()
						MCSCDatabase.close()
						result = tuple((0,False))
						self.outputLog_spigot.info_print("No new successful builds for BuildTools detected")
						return result
				return result

			@staticmethod
			def getBuildTools(url=None):
				'Obtains by downloading the last successful build from the jenkins'
				target_url = str(url) if url is not None else "https://hub.spigotmc.org/jenkins/view/Public/job/BuildTools/lastSuccessfulBuild/artifact/target/BuildTools.jar"
				response = requests.get(target_url)
				if response.status_code == 200:
					if os.path.isdir(str(program_folder) + "/build/BuildTools") == False:
						os.makedirs(str(program_folder) + "/build/BuildTools")
					with open(str(program_folder) + "/build/BuildTools/BuildTools.jar","wb") as buildtoolsjar:
						buildtoolsjar.write(response.content)
						buildtoolsjar.close()
				return

			def runBuildTools(self,parameter=None):
				'Runs Buildtools. If a parameter is given, Buildtools will run with the parameter'
				x = queue.Queue()
				def session():
					if parameter == None:
						process = subprocess.Popen(['java','-jar','BuildTools.jar'])
					else:
						process = subprocess.Popen(['java','-jar','BuildTools.jar',str(parameter)])
					returnCode = process.wait()
					x.put(returnCode)
					return
				
				with SoftwareSpec.changeDir(path=str(program_folder) + "/build/BuildTools/"):
					BuildToolsThread = threading.Thread(target=session,name="BuildToolsInstance")
					BuildToolsThread.start()
					BuildToolsThread.join()
					buildToolsThreadresult = x.get()
					if buildToolsThreadresult == 0:
						self.outputLog_spigot.info_print(f"Command exited with the return code of {buildToolsThreadresult}")
					return

			def getCraftbukkit(self,version=None,instance_name=None):
				'Installs the most current Spigot Version by passing the given Minecraft Version'
				try:
					if version is not None:
						if instance_name is not None:
							if os.path.isfile(str(program_folder) + "/build/BuildTools/BuildTools.jar") == True:
								outputdirectory = str(rootFilepath) + f"/base/sandbox/Instances/Vanilla/{instance_name}/"
								if not os.path.isdir(outputdirectory):
									os.makedirs(outputdirectory, exist_ok=True)
								parameterCmd = "--o", outputdirectory, "--rev", str(version), "--compile craftbukkit"
								self.runBuildTools(parameter=parameterCmd)
								return
							self.getBuildTools()
							self.getCraftbukkit(version=str(version),instance_name=str(instance_name))
							return
						raise MCSCInternalError(msg="Instance Name was expected, but got a NoneType value.")
					raise MCSCInternalError(msg="Version was expected, but got a NoneType value.")
				except MCSCInternalError as e:
					self.outputLog_spigot.error_print(e)
					return

			def getSpigot(self,version=None,instance_name=None):
				'Installs the most current Spigot Version by passing the given Minecraft Version'
				try:
					if version is not None:
						if instance_name is not None:
							if os.path.isfile(str(program_folder) + "/build/BuildTools/BuildTools.jar") == True:
								outputdirectory = str(rootFilepath) + f"/base/sandbox/Instances/Vanilla/{instance_name}/"
								if not os.path.isdir(outputdirectory):
									os.makedirs(outputdirectory, exist_ok=True)
								parameterCmd = "--o", outputdirectory, "--rev", str(version)
								self.runBuildTools(parameter=parameterCmd)
								return
							self.getBuildTools()
							self.getSpigot(version=str(version),instance_name=str(instance_name))
							return
						raise MCSCInternalError(msg="Instance Name was expected, but got a NoneType value.")
					raise MCSCInternalError(msg="Version was expected, but got a NoneType value.")
				except MCSCInternalError as e:
					self.outputLog_spigot.error_print(e)
					return

	class ForgeBaseClass():
		'Utility for handling Forge Updates'
		#Forge doesnt have a web-based API. Theres so little I can do in this dev stage
		def __init__(self):
			self.outputLog_forgeupdates = MCSCKernelCore(module="Updater",logic="Forge Updates")
			return

		@staticmethod
		def getmcVersionListing() -> list:
			'Returns a sorted list of compatible Minecraft Versions that forge works with using Curseforge\'s API'
			response = requests.get("https://api.curseforge.com/v1/minecraft/modloader",headers={"Accept": "application/json"})
			if response.status_code == 200:
				forgeRawData = response.json()
				forgeData = forgeRawData["data"]
				compatibleMCVersions = []
				for version in forgeData:
					mcVersion = version["gameVersion"]
					if mcVersion not in compatibleMCVersions:
						compatibleMCVersions.append(mcVersion)
				return sorted(compatibleMCVersions,key=lambda x: Version(x),reverse=True)
			return []

		def updateForgeVersionTable(self):
			'Checks for Forge Updates from Curseforge. When a new forge version is detected, the table is updated. When the table is updated, Minerva Server Crafter reboots.'
			result = (0,False)
			response = requests.get("https://api.curseforge.com/v1/minecraft/modloader",headers={"Accept": "application/json",'x-api-key': str(CurseforgeClass.decodeByteSecret())})
			if response.status_code == 200:
				forgeRawData = response.json()
				forgedata = forgeRawData["data"]
				currentforgeversions = {}
				for item in forgedata:
					forgeVersion = item["name"].split("forge-")[1]
					minecraftVersion = item["gameVersion"]
					if minecraftVersion in currentforgeversions:
						currentforgeversions[minecraftVersion].append(forgeVersion)
					else:
						currentforgeversions[minecraftVersion] = [forgeVersion]

				with SoftwareSpec.changeDir(path=str(rootFilepath)):
					MCSCDatabase = sqlite3.connect("mcsc_data.db")
					MCSC_Cursor = MCSCDatabase.cursor()
					MCSC_Cursor.execute("SELECT forgeversion, minecraftversion FROM forgeVersion_Table")
					existingVersions = {row[0]:row[1] for row in MCSC_Cursor.fetchall()}
					newVersions = [
						(forgeVersion, minecraftVersion)
						for minecraftVersion, forgeVersions in currentforgeversions.items()
						for forgeVersion in forgeVersions
						if forgeVersion not in existingVersions
					]
					totalNewVersions = len(newVersions)
					if newVersions:
						MCSC_Cursor.execute("DELETE FROM forgeVersion_Table")
						MCSCDatabase.commit()
						MCSC_Cursor.execute("VACUUM;")
						MCSCDatabase.commit()
						self.outputLog_forgeupdates.info_print(f"There are {totalNewVersions} total new version(s). Updating Table...")
						for minecraft_version, forge_version_list in sorted(currentforgeversions.items(), key=lambda x: Version(x[0]), reverse=True):
							for forge_version in forge_version_list:
								MCSC_Cursor.execute("INSERT INTO forgeVersion_Table VALUES (?, ?)", (forge_version, minecraft_version))
						for key, val in existingVersions.items():
							MCSC_Cursor.execute("INSERT INTO forgeVersion_Table VALUES (?, ?)",(key,val))
						MCSCDatabase.commit()
						MCSC_Cursor.close()
						MCSCDatabase.close()
						result = tuple((int(totalNewVersions),True))
						self.outputLog_forgeupdates.info_print("Version Table Updated.")
						return result
					MCSC_Cursor.close()
					MCSCDatabase.close()
					self.outputLog_forgeupdates.info_print("No new Forge Versions detected")
			return result

		@staticmethod
		def getForgeVersionsbyVersion(version) -> list:
			'Returns a list of Forge Versions thats compatiable with the given Minecraft Version'
			with SoftwareSpec.changeDir(path=str(rootFilepath)):
				MCSCDatabase = sqlite3.connect("mcsc_data.db")
				MCSC_Cursor = MCSCDatabase.cursor()
				MCSC_Cursor.execute("SELECT forgeversion FROM forgeVersion_Table WHERE minecraftversion = ?",(str(version),))
				forgeversionlist = [row[0] for row in MCSC_Cursor.fetchall()]
				MCSC_Cursor.close()
				MCSCDatabase.close()
				return forgeversionlist

	class FabricBaseClass():
		'Utility for handling Fabric Updates'
		def __init__(self):
			self.outputLog_fabricupdates = MCSCKernelCore(module="Updater",logic="Fabric Updates")
			return

		def updateFabricInstallerTable(self):
			'Checks for Fabric Installer updates'
			result = (0,False)
			with SoftwareSpec.changeDir(path=str(rootFilepath)):
				MCSCDatabase = sqlite3.connect('mcsc_data.db')
				MCSC_Cursor = MCSCDatabase.cursor()
				response = requests.get("https://maven.fabricmc.net/net/fabricmc/fabric-installer/maven-metadata.xml")
				if response.status_code == 200:
					xmlData = xmltodict.parse(response.content)
					installerversionList = xmlData["metadata"]['versioning']['versions']['version']
					fabricinstallerURLS = {str(item): f"https://maven.fabricmc.net/net/fabricmc/fabric-installer/{item}/" for item in installerversionList}
					MCSC_Cursor.execute("SELECT version FROM FabricInstallerVersion_Table")
					currentVersions = set(row[0] for row in MCSC_Cursor.fetchall())
					newVersions = [(installerversion, fabricinstallerURLS[installerversion]) for installerversion in installerversionList if installerversion not in currentVersions]
					totalUpdates = len(newVersions)
					if newVersions:
						self.outputLog_fabricupdates.info_print(f"There are {totalUpdates} total update(s). Updating Table...")
						MCSC_Cursor.execute("DELETE FROM FabricInstallerVersion_Table")
						MCSCDatabase.commit()
						MCSC_Cursor.execute("VACUUM;")
						MCSCDatabase.commit()
						for version, url in sorted(newVersions, key=lambda x: Version(x[0]), reverse=True):
							MCSC_Cursor.execute("INSERT INTO FabricInstallerVersion_Table (version,url) VALUES (?,?)",(version,url))
						MCSCDatabase.commit()
						MCSC_Cursor.close()
						MCSCDatabase.close()
						result = tuple((int(totalUpdates),True))
						self.outputLog_fabricupdates.info_print("Version Table has been successfully updated.")
						return result
					self.outputLog_fabricupdates.info_print("No new Fabric Installer versions detected")
				MCSC_Cursor.close()
				MCSCDatabase.close()
			return result

		@staticmethod
		def getInstallerListingfromTable() -> list:
			'Returns a complete list of applicable installer versions from the version Table'
			with SoftwareSpec.changeDir(path=str(rootFilepath)):
				MCSCDatabase = sqlite3.connect('mcsc_data.db')
				MCSC_Cursor = MCSCDatabase.cursor()
				MCSC_Cursor.execute('SELECT version FROM FabricInstallerVersion_Table')
				loaderListing = [loaderVersion[0] for loaderVersion in MCSC_Cursor.fetchall()]
				MCSC_Cursor.close()
				MCSCDatabase.close()
				return loaderListing

		@staticmethod
		def getInstallerURLPrefixListing() -> list:
			'Returns a complete list of applicable installer urls from the version Table. This does not provide the full url, just the pointer of base url'
			with SoftwareSpec.changeDir(path=str(rootFilepath)):
				MCSCDatabase = sqlite3.connect('mcsc_data.db')
				MCSC_Cursor = MCSCDatabase.cursor()
				MCSC_Cursor.execute('SELECT url FROM FabricInstallerVersion_Table')
				loaderListing = [loaderVersion[0] for loaderVersion in MCSC_Cursor.fetchall()]
				MCSC_Cursor.close()
				MCSCDatabase.close()
				return loaderListing

		def updateFabricVersions(self):
			'Checks for version updates for fabric using the Curseforge API'
			result = (0,False)
			headers = {"Accept": "application/json",'x-api-key': str(CurseforgeClass.decodeByteSecret())}
			response = requests.get("https://api.curseforge.com/v1/minecraft/modloader",headers=headers,params={'includeAll': True})
			if response.status_code == 200:
				rawFabricVersionData = response.json()
				fabricVersionData = rawFabricVersionData['data']
				currentfabricVersions = {}
				for item in fabricVersionData:
					name = item['name']
					if name.startswith('fabric-') == True:
						fabricversiondata = name.split('-')
						fabricVersion = fabricversiondata[1]
						minecraftVersion = fabricversiondata[2]
						if fabricVersion not in currentfabricVersions.keys():
							currentfabricVersions[str(fabricVersion)] = []
						currentfabricVersions[str(fabricVersion)].append(minecraftVersion)
				with SoftwareSpec.changeDir(path=str(rootFilepath)):
					MCSCDatabase = sqlite3.connect("mcsc_data.db")
					MCSC_Cursor = MCSCDatabase.cursor()
					MCSC_Cursor.execute("SELECT version, compatiableMinecraftVersions FROM fabricVersion_Table")
					versionTableData = {row[0]: row[1] for row in MCSC_Cursor.fetchall()}
					newversions = [version for version in currentfabricVersions.keys() if version not in versionTableData.keys()]
					totalupdates = len(newversions)
					if newversions:
						self.outputLog_fabricupdates.info_print(f"There are {totalupdates} new version update(s). Updating Table...")
						MCSC_Cursor.execute("DELETE FROM fabricVersion_Table")
						MCSCDatabase.commit()
						MCSC_Cursor.execute("VACUUM;")
						MCSCDatabase.commit()
						for key, val in currentfabricVersions.items():
							MCSC_Cursor.execute("INSERT INTO fabricVersion_Table (version,compatiableMinecraftVersions) VALUES (?,?)", (key,str(val)))
						for key, val in versionTableData.items():
							MCSC_Cursor.execute("INSERT INTO fabricVersion_Table (version,compatiableMinecraftVersions) VALUES (?,?)", (key,str(val)))
						self.outputLog_fabricupdates.info_print("Version Table has been successfully updated.")
						MCSCDatabase.commit()
						MCSC_Cursor.close()
						MCSCDatabase.close()
						result = tuple((int(totalupdates),True))
						return result
					MCSC_Cursor.close()
					MCSCDatabase.close()
					self.outputLog_fabricupdates.info_print("No new Fabric Versions detected")
			return result
if not os.path.isfile(str(program_folder) + "/build/BuildTools/BuildTools.jar"):
	if not os.path.isdir(str(program_folder) + "/build"):
		os.makedirs(str(program_folder) + "/build",exist_ok=True)
		os.makedirs(str(program_folder) + "/build/BuildTools",exist_ok=True)
	MCSCDatabase = sqlite3.connect("mcsc_data.db")
	MCSC_Cursor = MCSCDatabase.cursor()
	outputLog_updater.info_print("BuildTools is missing! Obtaining...")
	#We need to fetch the last successful build from the database table
	MCSC_Cursor.execute("SELECT Url FROM BuildTools_SuccessfulBuildVerified_Table ORDER BY CAST(BuildID AS INTEGER) DESC LIMIT 1")
	latestBuild = MCSC_Cursor.fetchone()[0]
	if latestBuild:
		latestBuild_url = latestBuild + "artifact/target/BuildTools.jar"
		MCSCUpdater.SpigotBaseClass.getBuildTools(url=str(latestBuild_url))
		MCSC_Cursor.close()
		MCSCDatabase.close()
if not os.path.isdir(str(rootFilepath) + "/base/sandbox/Instances"):
	#Generate them
	os.mkdir(str(rootFilepath) + "/base/sandbox/Instances")
	os.mkdir(str(rootFilepath) + "/base/sandbox/Instances/Vanilla")
	os.mkdir(str(rootFilepath) + "/base/sandbox/Instances/Modded")
	os.mkdir(str(rootFilepath) + "/base/sandbox/Instances/Custom")
	os.mkdir(str(rootFilepath) + "/base/sandbox/Instances/Curseforge")
	os.mkdir(str(rootFilepath) + "/base/sandbox/Instances/Curseforge/Modpacks")
	os.mkdir(str(rootFilepath) + "/base/sandbox/Instances/Curseforge/imported")
	os.mkdir(str(rootFilepath) + "/base/sandbox/Instances/Curseforge/downloads")

outputLog_updater.info_print("Loaded Updater Logic.")
