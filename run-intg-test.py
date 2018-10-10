# Copyright (c) 2018, WSO2 Inc. (http://wso2.com) All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# importing required modules
import sys
from xml.etree import ElementTree as ET
import subprocess
import wget
import logging
import inspect
import os
import shutil
import pymysql
import sqlparse
import stat
import re
import fnmatch
from pathlib import Path
import urllib.request as urllib2
from xml.dom import minidom
import common as cm
import errno
from subprocess import Popen, PIPE

from const_ei import DB_META_DATA, ARTIFACT_REPORTS_PATHS, DIST_POM_PATH, LIB_PATH, M2_PATH, INTEGRATION_PATH, IGNORE_DIR_TYPES, \
    TESTNG_DIST_XML_PATHS, DISTRIBUTION_PATH, DATASOURCE_PATHS, POM_FILE_PATHS, INTEGRATOR, BP, BROKER, ANALYTICS, MICRO_INTG

from const_common import NS, ZIP_FILE_EXTENSION, CARBON_NAME, VALUE_TAG, SURFACE_PLUGIN_ARTIFACT_ID, TEST_PLAN_PROPERTY_FILE_NAME, \
    INFRA_PROPERTY_FILE_NAME, LOG_FILE_NAME, PRODUCT_STORAGE_DIR_NAME, DEFAULT_DB_USERNAME, LOG_STORAGE, TEST_OUTPUT_DIR_NAME, \
    DEFAULT_ORACLE_SID, MYSQL_DB_ENGINE, ORACLE_DB_ENGINE, PRODUCT_STORAGE_DIR_NAME, MSSQL_DB_ENGINE



#workspace = None
#dist_name = None
#product_id = None
test_mode = None
#product_version = None
#database_config = {}
storage_dir_abs_path = None
database_names = []
db_engine = None
sql_driver_location = None



## This method should be converted using inheritance
## and thereafter remove/modify the code block from here
def add_distribution_to_m2(storage, name, product_version):
    """Add the distribution zip into local .m2.
    """
    home = Path.home()
    m2_rel_path = ".m2/repository/org/wso2/" + M2_PATH[product_id]
    linux_m2_path = home / m2_rel_path / product_version / name
    windows_m2_path = Path("/Documents and Settings/Administrator/" + m2_rel_path + "/" + product_version + "/" + name)
    if sys.platform.startswith('win'):
        windows_m2_path = cm.winapi_path(windows_m2_path)
        storage = cm.winapi_path(storage)
        cm.compress_distribution(windows_m2_path, storage)
        shutil.rmtree(windows_m2_path, onerror=cm.on_rm_error)
    else:
        cm.compress_distribution(linux_m2_path, storage)
        shutil.rmtree(linux_m2_path, onerror=cm.on_rm_error)



## This method should be converted using inheritance
## and thereafter remove/modify the code block from here
def modify_datasources():
    """Modify datasources files which are defined in the const.py. DB ulr, uname, pwd, driver class values are modifying.
    """
    profiles = DATASOURCE_PATHS[product_id]
    for key, value in profiles.items():
        for data_source in value:
            file_path = Path(storage_dist_abs_path / data_source)
            if sys.platform.startswith('win'):
                file_path = cm.winapi_path(file_path)
            logger.info("Modifying datasource: " + str(file_path))
            artifact_tree = ET.parse(file_path)
            artifarc_root = artifact_tree.getroot()
            data_sources = artifarc_root.find('datasources')
            for item in data_sources.findall('datasource'):
                database_name = None
                for child in item:
                    if child.tag == 'name':
                        database_name = child.text + "_" + key
                    # special checking for namespace object content:media
                    if child.tag == 'definition' and database_name:
                        configuration = child.find('configuration')
                        url = configuration.find('url')
                        user = configuration.find('username')
                        password = configuration.find('password')
                        validation_query = configuration.find('validationQuery')
                        drive_class_name = configuration.find('driverClassName')
                        if MYSQL_DB_ENGINE == database_config['db_engine'].upper():
                            url.text = url.text.replace(url.text, database_config[
                                'url'] + "/" + database_name + "?autoReconnect=true&useSSL=false&requireSSL=false&"
                                                               "verifyServerCertificate=false")
                            user.text = user.text.replace(user.text, database_config['user'])
                        elif ORACLE_DB_ENGINE == database_config['db_engine'].upper():
                            url.text = url.text.replace(url.text, database_config['url'] + "/" + DEFAULT_ORACLE_SID)
                            user.text = user.text.replace(user.text, database_name)
                            validation_query.text = validation_query.text.replace(validation_query.text,
                                                                                  "SELECT 1 FROM DUAL")
                        elif MSSQL_DB_ENGINE == database_config['db_engine'].upper():
                            url.text = url.text.replace(url.text,
                                                        database_config['url'] + ";" + "databaseName=" + database_name)
                            user.text = user.text.replace(user.text, database_config['user'])
                        else:
                            url.text = url.text.replace(url.text, database_config['url'] + "/" + database_name)
                            user.text = user.text.replace(user.text, database_config['user'])
                        password.text = password.text.replace(password.text, database_config['password'])
                        drive_class_name.text = drive_class_name.text.replace(drive_class_name.text,
                                                                              database_config['driver_class_name'])
                        database_names.append(database_name)
            artifact_tree.write(file_path)



def configure_product(name, id, db_config, ws, product_version):
    try:
        global dist_name
        global product_id
        global database_config
        global workspace
        global target_dir_abs_path
        global storage_dist_abs_path
        global storage_dir_abs_path

        dist_name = name
        product_id = id
        database_config = db_config
        workspace = ws
        zip_name = str(dist_name) + ZIP_FILE_EXTENSION

        storage_dir_abs_path = Path(workspace + "/" + PRODUCT_STORAGE_DIR_NAME)
        target_dir_abs_path = Path(workspace + "/" + product_id + "/" + DISTRIBUTION_PATH[product_id])
        storage_zip_abs_path = Path(storage_dir_abs_path / zip_name)
        storage_dist_abs_path = Path(storage_dir_abs_path / dist_name)
        configured_dist_storing_loc = Path(target_dir_abs_path / dist_name)
        script_name = [INTEGRATOR, BP, BROKER, ANALYTICS, MICRO_INTG]

        cm.extract_product(storage_zip_abs_path)
        for scripts in script_name:
            script_path = Path(storage_dist_abs_path / Path(scripts))
            cm.attach_jolokia_agent(script_path)

        cm.copy_jar_file(Path(database_config['sql_driver_location']), Path(storage_dist_abs_path / LIB_PATH[product_id]))
        modify_datasources()
        os.remove(str(storage_zip_abs_path))
        cm.compress_distribution(configured_dist_storing_loc, storage_dir_abs_path)
        add_distribution_to_m2(storage_dir_abs_path, dist_name, product_version)
        shutil.rmtree(configured_dist_storing_loc, onerror=cm.on_rm_error)
        return database_names
    except FileNotFoundError as e:
        logger.error("Error occurred while finding files", exc_info=True)
    except IOError as e:
        logger.error("Error occurred while accessing files", exc_info=True)
    except Exception as e:
        logger.error("Error occurred while configuring the product", exc_info=True)


# Since we have added a method to clone a given git branch and checkout to the latest released tag it is not required to
# modify pom files. Hence in the current implementation this method is not using.
# However, in order to execute this method you can define pom file paths in const_<prod>.py as a constant
# and import it to run-intg-test.py. Thereafter assign it to global variable called pom_file_paths in the
# configure_product method and call the modify_pom_files method.
def modify_pom_files():
    for pom in POM_FILE_PATHS:
        file_path = Path(workspace + "/" + product_id + "/" + pom)
        if sys.platform.startswith('win'):
            file_path = cm.winapi_path(file_path)
        logger.info("Modifying pom file: " + str(file_path))
        ET.register_namespace('', NS['d'])
        artifact_tree = ET.parse(file_path)
        artifarct_root = artifact_tree.getroot()
        data_sources = artifarct_root.find('d:build', NS)
        plugins = data_sources.find('d:plugins', NS)
        for plugin in plugins.findall('d:plugin', NS):
            artifact_id = plugin.find('d:artifactId', NS)
            if artifact_id is not None and artifact_id.text == SURFACE_PLUGIN_ARTIFACT_ID:
                configuration = plugin.find('d:configuration', NS)
                system_properties = configuration.find('d:systemProperties', NS)
                for neighbor in system_properties.iter('{' + NS['d'] + '}' + CARBON_NAME):
                    neighbor.text = cm.modify_distribution_name(neighbor)
                for prop in system_properties:
                    name = prop.find('d:name', NS)
                    if name is not None and name.text == CARBON_NAME:
                        for data in prop:
                            if data.tag == VALUE_TAG:
                                data.text = cm.modify_distribution_name(data)
                break
        artifact_tree.write(file_path)


## This method should be converted using inheritance
## and thereafter remove/modify the code block from here
def save_log_files():
    log_storage = Path(workspace + "/" + LOG_STORAGE)
    if not Path.exists(log_storage):
        Path(log_storage).mkdir(parents=True, exist_ok=True)
    log_file_paths = ARTIFACT_REPORTS_PATHS[product_id]
    if log_file_paths:
        for file in log_file_paths:
            absolute_file_path = Path(workspace + "/" + product_id + "/" + file)
            if Path.exists(absolute_file_path):
                copy_file(absolute_file_path, log_storage)
            else:
                logger.error("File doesn't contain in the given location: " + str(absolute_file_path))


## This method should be converted using inheritance
## and thereafter remove/modify the code block from here
# def get_db_meta_data(argument):
#     switcher = DB_META_DATA
#     return switcher.get(argument, False)


## This method should be converted using inheritance
## and thereafter remove/modify the code block from here
def copy_file(source, target):
    """Copy the source file to the target.
    """
    try:
        if sys.platform.startswith('win'):
            source = cm.winapi_path(source)
            target = cm.winapi_path(target)

        if os.path.isdir(source):
            shutil.copytree(source, target, ignore=cm.ignore_dirs((IGNORE_DIR_TYPES[product_id])))
        else:
            shutil.copy(source, target)
    except OSError as e:
        print('Directory not copied. Error: %s' % e)



## This method should be converted using inheritance
## and thereafter remove/modify the code block from here
def save_test_output():
    log_folder = Path(workspace + "/" + TEST_OUTPUT_DIR_NAME)
    if Path.exists(log_folder):
        shutil.rmtree(log_folder)
    log_file_paths = ARTIFACT_REPORTS_PATHS[product_id]
    for key, value in log_file_paths.items():
        for file in value:
            absolute_file_path = Path(workspace + "/" + product_id + "/" + file)
            if Path.exists(absolute_file_path):
                log_storage = Path(workspace + "/" + TEST_OUTPUT_DIR_NAME + "/" + key)
                copy_file(absolute_file_path, log_storage)
            else:
                logger.error("File doesn't contain in the given location: " + str(absolute_file_path))


## This method should be converted using inheritance
## and thereafter remove/modify the code block from here
def build_snapshot_dist():
    """Build the distribution
    """
    zip_name = dist_name + ZIP_FILE_EXTENSION
    try:
        snapshot_build_dir_path = Path(workspace + "/" + product_id + "/")
        subprocess.call(['mvn', 'clean', 'install', '-Dmaven.test.skip=true', '-fae', '-B',
                         '-Dorg.slf4j.simpleLogger.log.org.apache.maven.cli.transfer.Slf4jMavenTransferListener=warn'], cwd=snapshot_build_dir_path)
        logger.info("Snapshot distribution build successfully")
    except Exception as e:
        logger.error("Error occurred while build the distribution",
                     exc_info=True)

    # copy the zip file to storage
    storage_dir_path = Path(workspace + "/" + PRODUCT_STORAGE_DIR_NAME)
    built_dir_path = Path(workspace + "/" + product_id + "/" + DISTRIBUTION_PATH[product_id])
    built_zip_abs_path = Path(built_dir_path / zip_name)

    if os.path.exists(built_zip_abs_path):
        shutil.copy2(built_zip_abs_path, storage_dir_path)
        os.remove(built_zip_abs_path)
    else:
        print("The file does not exist")

## This method should be converted using inheritance
## and thereafter remove/modify the code block from here
# def set_custom_testng():
#     if use_custom_testng_file == "TRUE":
#         testng_source = Path(workspace + "/" + "testng.xml")
#         testng_destination = Path(workspace + "/" + product_id + "/" + TESTNG_DIST_XML_PATH)
#         testng_server_mgt_source = Path(workspace + "/" + "testng-server-mgt.xml")
#         testng_server_mgt_destination = Path(workspace + "/" + product_id + "/" + TESTNG_SERVER_MGT_DIST)
#         # replace testng source
#         replace_file(testng_source, testng_destination)
#         # replace testng server mgt source
# replace_file(testng_server_mgt_source, testng_server_mgt_destination)





def main():
    try:
        global logger
        global dist_name
        logger = cm.function_logger(logging.DEBUG, logging.DEBUG)
        print(str(sys.version_info))
        if sys.version_info < (3, 6):
            raise Exception(
                "To run run-intg-test.py script you must have Python 3.6 or latest. Current version info: " + sys.version_info)
        cm.read_proprty_files()
        if not cm.validate_property_readings():
            raise Exception(
                "Property file doesn't have mandatory key-value pair. Please verify the content of the property file "
                "and the format")
        # construct database configuration
        cm.construct_db_config()
        # clone the repository
        cm.clone_repo()
        # set the custom testng.xml or the product testng.xml
        #set_custom_testng()

        #--Removing DEBUG test_mode

        if test_mode == "RELEASE":
            cm.checkout_to_tag(cm.get_latest_tag_name(product_id))
            dist_name = cm.get_dist_name()
            cm.get_latest_released_dist()
        elif test_mode == "SNAPSHOT":
            dist_name = cm.get_dist_name()
        #++Adding a method to build distribution, and remove the latest_stable_distribution
            build_snapshot_dist()
        elif test_mode == "WUM":
            # todo after identify specific steps that are related to WUM, add them to here
            dist_name = cm.get_dist_name()
            logger.info("WUM specific steps are empty")

        # populate databases

        db_names = configure_product(cm.dist_name, cm.product_id, cm.database_config, cm.workspace, cm.product_version)
        if db_names is None or not db_names:
            raise Exception("Failed the product configuring")
        cm.setup_databases(db_names)
        if product_id == "product-apim":
            module_path = Path(workspace + "/" + product_id + "/" + 'modules/api-import-export')
            cm.build_module(module_path)
        intg_module_path = Path(workspace + "/" + product_id + "/" + INTEGRATION_PATH[product_id])
        #cm.build_module(intg_module_path)
        #cm.save_test_output()
        #cm.create_output_property_fle()
    except Exception as e:
        logger.error("Error occurred while running the run-intg.py script", exc_info=True)
    except BaseException as e:
        logger.error("Error occurred while doing the configuration", exc_info=True)


if __name__ == "__main__":
    main()
