##
# File: ReferenceSequenceAssignmentAdapter.py
# Date: 8-Oct-2019  jdw
#
# Selected utilities to update reference sequence assignments information
# in the core_entity collection.
#
# Updates:
#
##
__docformat__ = "restructuredtext en"
__author__ = "John Westbrook"
__email__ = "jwest@rcsb.rutgers.edu"
__license__ = "Apache 2.0"

import copy
import logging

from rcsb.exdb.utils.ObjectAdapterBase import ObjectAdapterBase

logger = logging.getLogger(__name__)


class ReferenceSequenceAssignmentAdapter(ObjectAdapterBase):
    """  Selected utilities to update reference sequence assignments information
         in the core_entity collection.

        "pdbx_ec" : "5.2.1.8",
        "rcsb_ec_lineage" : [
            {
                "id" : "5",
                "depth" : NumberInt(1),
                "name" : "Isomerases"
            },
            {
                "id" : "5.2",
                "depth" : NumberInt(2),
                "name" : "cis-trans-Isomerases"
            },
            {
                "id" : "5.2.1",
                "depth" : NumberInt(3),
                "name" : "cis-trans Isomerases (only sub-subclass identified to date)"
            },
            {
                "id" : "5.2.1.8",
                "depth" : NumberInt(4),
                "name" : "peptidylprolyl isomerase"
            }
        ],
    """

    def __init__(self, refSeqAssignProvider):
        super(ReferenceSequenceAssignmentAdapter, self).__init__()
        #
        self.__rsaP = refSeqAssignProvider
        self.__ssP = self.__rsaP.getSiftsSummaryProvider()
        self.__ecP = self.__rsaP.getEcProvider()
        self.__refD = self.__rsaP.getRefData()
        self.__matchD = self.__rsaP.getMatchInfo()
        #

    def filter(self, obj, **kwargs):
        isTestMode = False
        if isTestMode:
            ok1, tObj = self.__filterAccessions(copy.deepcopy(obj))
            ok2, tObj = self.__filterFeatures(tObj)
            return ok1 and ok2, obj
        else:
            ok1, obj = self.__filterAccessions(obj)
            ok2, obj = self.__filterFeatures(obj)
            return ok1 and ok2, obj

    def __filterFeatures(self, obj):
        ok = True
        try:
            if not ("rcsb_polymer_entity_container_identifiers" in obj and "rcsb_id" in obj):
                return False, obj
            entityKey = obj["rcsb_id"]
            eciD = obj["rcsb_polymer_entity_container_identifiers"]
            #
            logger.debug(" ------------- Running feature filter on %r --------------", entityKey)
            #
            rsDL = []
            soDL = []
            #
            try:
                rsDL = eciD["reference_sequence_identifiers"]
            except Exception:
                pass
            #
            # try:
            #    raDL = eciD["related_annotation_identifiers"]
            # except Exception:
            #     pass

            try:
                soDL = obj["rcsb_entity_source_organism"]
            except Exception:
                pass
            #
            try:
                peObj = obj["rcsb_polymer_entity"]
            except Exception:
                pass
            # rsD {'database_name': 'UniProt', 'database_accession': 'P06881', 'provenance_source': 'PDB'}
            unpIdS = set()
            for rsD in rsDL:
                if "database_name" in rsD and rsD["database_name"] == "UniProt" and "database_accession" in rsD:
                    unpIdS.add(rsD["database_accession"])
            #
            unpGeneDL = []
            unpAnnDL = []
            goIdL = []

            for unpId in unpIdS:
                uD = self.__refD[unpId] if unpId in self.__refD else None
                if not uD:
                    logger.info("%s no data for unexpected UniProt accession %r", entityKey, unpId)
                    continue
                if "gene" in uD and "taxonomy_id" in uD:
                    taxId = int(uD["taxonomy_id"])
                    logger.debug("%s : %r gene names %r", entityKey, unpId, uD["gene"])
                    for tD in uD["gene"]:
                        unpGeneDL.append({"provenance_code": "UniProt", "value": tD["name"], "taxonomy_id": taxId})
                if "dbReferences" in uD:
                    logger.debug("%s : %r references %d", entityKey, unpId, len(uD["dbReferences"]))
                    for tD in uD["dbReferences"]:
                        if "resource" in tD and "id_code" in tD and tD["resource"] in ["GO", "Pfam", "InterPro"]:
                            if tD["resource"] in ["GO"]:
                                if self.__rsaP.goIdExists(tD["id_code"]):
                                    goIdL.append(tD["id_code"])
                                else:
                                    continue
                            unpAnnDL.append({"provenance_source": "UniProt", "resource_identifier": tD["id_code"], "resource_name": tD["resource"]})

            #
            # raD {'resource_identifier': 'PF00503', 'provenance_source': 'SIFTS', 'resource_name': 'Pfam'}
            # "provenance_source":  <"PDB"|"RCSB"|"SIFTS"|"UniProt"> "GO", "InterPro", "Pfam"
            #
            # for ii, raD in enumerate(raDL):
            #    logger.info("raD (%d) related annotation %r", ii, raD["resource_name"])
            # ------------
            # filter existing annotations
            if "related_annotation_identifiers" in eciD:
                qL = []
                for qD in eciD["related_annotation_identifiers"]:
                    if qD["provenance_source"] != "UniProt":
                        qL.append(qD)
                eciD["related_annotation_identifiers"] = qL

            for unpAnnD in unpAnnDL:
                eciD.setdefault("related_annotation_identifiers", []).append(unpAnnD)
            #
            if goIdL:
                goLin = []
                goLin = self.__rsaP.getGeneOntologyLineage(goIdL)
                if goLin:
                    eciD["related_annotation_lineage"] = goLin
            #
            # --------------  Add gene names -----------------
            #
            numSource = len(soDL)
            logger.debug("%s unpGeneDL %r", entityKey, unpGeneDL)
            for ii, soD in enumerate(soDL):
                if "ncbi_taxonomy_id" not in soD:
                    continue
                logger.debug("soD (%d) taxonomy %r", ii, soD["ncbi_taxonomy_id"])
                # Filter any existing annotations
                if "rcsb_gene_name" in soD:
                    qL = []
                    for qD in soD["rcsb_gene_name"]:
                        if qD["provenance_code"] != "UniProt":
                            qL.append(qD)
                    soD["rcsb_gene_name"] = qL
                taxId = soD["ncbi_taxonomy_id"]
                for unpGeneD in unpGeneDL:
                    # Only for matching taxonomies
                    if taxId == unpGeneD["taxonomy_id"]:
                        # skip cases with primary annotations and multiple sources
                        if "rcsb_gene_name" in soD and numSource > 1:
                            logger.warning("%s skipping special chimeric case", entityKey)
                            continue
                        soD.setdefault("rcsb_gene_name", []).append({"provenance_code": unpGeneD["provenance_code"], "value": unpGeneD["value"]})
                #
                # Remapping/extending EC assignments.
                if peObj:
                    linL = []
                    enzD = {}
                    if "rcsb_enzyme_class_combined" in peObj:
                        logger.debug("%s PDB EC assignment %r", entityKey, peObj["rcsb_enzyme_class_combined"])
                        enzD = {tD["ec"]: tD["provenance_source"] for tD in peObj["rcsb_enzyme_class_combined"]}
                        logger.info("%s PDB EC assignment mapped %r", entityKey, enzD)
                    #
                    unpEcD = {}
                    for unpId in unpIdS:
                        uD = self.__refD[unpId] if unpId in self.__refD else None
                        if not uD:
                            logger.info("%s no data for unexpected UniProt accession %r", entityKey, unpId)
                            continue
                        if "dbReferences" in uD:
                            logger.debug("%s : %r references %d", entityKey, unpId, len(uD["dbReferences"]))
                            for tD in uD["dbReferences"]:
                                if "resource" in tD and "id_code" in tD and tD["resource"] in ["EC"]:
                                    logger.debug("%s UniProt accession %r EC %r", entityKey, unpId, tD)
                                    tEc = self.__ecP.normalize(tD["id_code"])
                                    if self.__ecP.exists(tEc):
                                        unpEcD[tEc] = "UniProt"
                    # integrate the UniProt data and update the object -
                    if unpEcD:
                        logger.info("%s UniProt EC assignment %r", entityKey, unpEcD)
                        for ecId in unpEcD:
                            if ecId in enzD:
                                continue
                            enzD[ecId] = unpEcD[ecId]
                        for ecId in enzD:
                            tL = self.__ecP.getLineage(ecId)
                            if tL:
                                linL.extend(tL)
                        peObj["rcsb_enzyme_class_combined"] = [{"ec": k, "provenance_source": v} for k, v in enzD.items()]
                        peObj["rcsb_ec_lineage"] = [{"depth": tup[0], "id": tup[1], "name": tup[2]} for tup in linL]
                    #
        except Exception as e:
            ok = False
            logger.exception("Feature filter adapter failing with error with %s", str(e))
        #
        return ok, obj

    def __filterAccessions(self, obj):
        ok = True
        try:
            entityKey = obj["rcsb_id"]
            logger.debug(" ------------- Running accession filter on %r --------------", entityKey)
            #
            referenceDatabaseName = "UniProt"
            provSourceL = ["PDB"]
            alignDL = None
            ersDL = None
            authAsymIdL = None
            taxIdL = None
            try:
                ersDL = obj["rcsb_polymer_entity_container_identifiers"]["reference_sequence_identifiers"]
                authAsymIdL = obj["rcsb_polymer_entity_container_identifiers"]["auth_asym_ids"]
            except Exception:
                logger.debug("%s no reference assignment protein sequence.", entityKey)

            #
            try:
                taxIdL = [oD["ncbi_taxonomy_id"] for oD in obj["rcsb_entity_source_organism"]]
                taxIdL = list(set(taxIdL))
                logger.debug("%s taxonomy (%d) %r", entityKey, len(taxIdL), taxIdL)
            except Exception as e:
                logger.debug("Failing with %s", str(e))
            #
            if ersDL:
                retDL = []
                dupD = {}
                for ersD in ersDL:
                    isMatchedRefDb, isMatchedAltDb, updErsD = self.__reMapAccessions(entityKey, ersD, referenceDatabaseName, taxIdL, provSourceL)
                    #
                    logger.debug("isMatchedRefDb %r isMatchedAltDb %r updErsD %r", isMatchedRefDb, isMatchedAltDb, updErsD)

                    if (isMatchedRefDb or isMatchedAltDb) and updErsD["database_accession"] not in dupD:
                        dupD[updErsD["database_accession"]] = True
                        retDL.append(updErsD)
                    #
                    if not isMatchedRefDb and entityKey not in dupD:
                        dupD[entityKey] = True
                        siftsAccDL = self.__getSiftsAccessions(entityKey, authAsymIdL)
                        for siftsAccD in siftsAccDL:
                            logger.info("Using/adding SIFTS accession mapping for %s", entityKey)
                            retDL.append(siftsAccD)
                        if not siftsAccDL:
                            logger.info("No alternative SIFTS accession mapping for %s", entityKey)

                if retDL:
                    logger.debug("%s retDL %r", entityKey, retDL)
                    obj["rcsb_polymer_entity_container_identifiers"]["reference_sequence_identifiers"] = retDL
                else:
                    del obj["rcsb_polymer_entity_container_identifiers"]["reference_sequence_identifiers"]
                    logger.info("Incomplete reference sequence mapping update for %s", entityKey)
            #
            try:
                alignDL = obj["rcsb_polymer_entity_align"]
            except Exception:
                pass
            if alignDL and authAsymIdL:
                retDL = []
                dupD = {}
                for alignD in alignDL:
                    isMatchedRefDb, isMatchedAltDb, updAlignD, alignHash = self.__reMapAlignments(entityKey, alignD, referenceDatabaseName, taxIdL, provSourceL)
                    #
                    if (isMatchedRefDb or isMatchedAltDb) and alignHash not in dupD:
                        if alignHash:
                            dupD[alignHash] = True
                        retDL.append(updAlignD)
                    #

                    if not isMatchedRefDb and entityKey not in dupD:
                        dupD[entityKey] = True
                        siftsAlignDL = self.__getSiftsAlignments(entityKey, authAsymIdL)
                        for siftsAlignD in siftsAlignDL:
                            logger.info("Using/adding SIFTS mapping for the alignment of %s", entityKey)
                            retDL.append(siftsAlignD)
                        if not siftsAlignDL:
                            logger.info("No alternative SIFTS alignment for %s", entityKey)
                    #
                if retDL:
                    logger.debug("%s retDL %r", entityKey, retDL)
                    obj["rcsb_polymer_entity_align"] = retDL
                else:
                    del obj["rcsb_polymer_entity_align"]
                    logger.info("Incomplete reference sequence alignment update for %s", entityKey)
        except Exception as e:
            ok = False
            logger.exception("Filter adapter failing with error with %s", str(e))
        #
        return ok, obj

    def __reMapAccessions(self, entityKey, rsiD, referenceDatabaseName, taxIdL, provSourceL, excludeReferenceDatabases=None):
        """Internal method to re-map accession for the input database and assignment source

        Args:
            rsiDL (list): current list of accession
            databaseName (str, optional): resource database name. Defaults to 'UniProt'.
            provSource (str, optional): assignment provenance. Defaults to 'PDB'.

        Returns:
            bool, bool, dict: flag for mapping success, flag for a supported reference database,
                              and remapped (and unmapped) accessions in the input object list

        Example:
                    "P14118": {
                    "searchId": "P14118",
                    "matchedIds": {
                        "P84099": {
                        "taxId": 10090
                        },
                        "P84100": {
                        "taxId": 10116
                        },
                        "P84098": {
                        "taxId": 9606
                        }
                    },
                    "matched": "secondary"
                },
        """
        isMatchedRefDb = False
        isMatchedAltDb = False
        excludeReferenceDatabases = excludeReferenceDatabases if excludeReferenceDatabases else ["PDB"]
        refDbList = ["UniProt", "GenBank", "EMBL", "NDB", "NORINE", "PIR", "PRF", "RefSeq"]
        #
        rId = rsiD["database_accession"]
        logger.debug("%s rId %r db %r prov %r", entityKey, rId, rsiD["database_name"], rsiD["provenance_source"])
        #
        if rsiD["database_name"] in excludeReferenceDatabases:
            isMatchedAltDb = False
        elif rsiD["database_name"] == referenceDatabaseName and rsiD["provenance_source"] in provSourceL:
            try:
                if rId in self.__matchD and self.__matchD[rId]["matched"] in ["primary"]:
                    # no change
                    isMatchedRefDb = True
                elif rId in self.__matchD and self.__matchD[rId]["matched"] in ["secondary"]:
                    logger.debug("secondary %r matched len %d", self.__matchD[rId]["matched"], len(self.__matchD[rId]["matchedIds"]))
                    if len(self.__matchD[rId]["matchedIds"]) == 1:
                        for mId, mD in self.__matchD[rId]["matchedIds"].items():
                            rsiD["database_accession"] = mId
                            logger.info("%s matched secondary %s -> %s", entityKey, rId, mId)
                            isMatchedRefDb = True
                    elif taxIdL and len(taxIdL) == 1:
                        #  -- simplest match case --
                        numM = 0
                        for mId, mD in self.__matchD[rId]["matchedIds"].items():
                            if taxIdL[0] == mD["taxId"]:
                                rsiD["database_accession"] = mId
                                numM += 1
                        if numM == 1:
                            isMatchedRefDb = True
                            logger.info("%s matched secondary with taxId %r %s -> %s", entityKey, taxIdL[0], rId, rsiD["database_accession"])
                    elif not taxIdL:
                        logger.info("%s no taxids with UniProt (%s) secondary mapping", entityKey, rId)
                    else:
                        logger.info("%s ambiguous mapping for a UniProt (%s) secondary mapping - taxIds %r", entityKey, rId, taxIdL)
                #
            except Exception:
                pass

        elif rsiD["provenance_source"] in provSourceL and rsiD["database_name"] in refDbList:
            logger.info("%s leaving reference accession for %s %s assigned by %r", entityKey, rId, rsiD["database_name"], provSourceL)
            isMatchedRefDb = True
        else:
            logger.info("%s leaving a reference accession for %s %s assigned by %r", entityKey, rId, rsiD["database_name"], rsiD["provenance_source"])
        #
        logger.debug("%s isMatched %r isExcluded %r for accession %r", entityKey, isMatchedRefDb, isMatchedAltDb, rId)
        #
        return isMatchedRefDb, isMatchedAltDb, rsiD

    def __reMapAlignments(self, entityKey, alignD, referenceDatabaseName, taxIdL, provSourceL, excludeReferenceDatabases=None):
        """Internal method to re-map alignments for the input databae and assignment source

        Args:
            alignD (dict): alignment object including accession and aligned regions
            databaseName (str, optional): resource database name. Defaults to 'UniProt'.
            provSourceL (list, optional): assignment provenance. Defaults to 'PDB'.

        Returns:
            bool, bool, list: flag for mapping success (refdb), flag for mapping success (altdb),
                               and remapped (and unmapped) accessions in the input align list
        """
        isMatchedAltDb = False
        isMatchedRefDb = False
        excludeReferenceDatabases = excludeReferenceDatabases if excludeReferenceDatabases else ["PDB"]
        refDbList = ["UniProt", "GenBank", "EMBL", "NDB", "NORINE", "PIR", "PRF", "RefSeq"]
        provSourceL = provSourceL if provSourceL else []
        rId = alignD["reference_database_accession"]
        #
        if alignD["reference_database_name"] in excludeReferenceDatabases:
            isMatchedAltDb = False
        elif alignD["reference_database_name"] == referenceDatabaseName and alignD["provenance_code"] in provSourceL:
            try:
                if rId in self.__matchD and self.__matchD[rId]["matched"] in ["primary"]:
                    # no change
                    isMatchedRefDb = True
                elif rId in self.__matchD and self.__matchD[rId]["matched"] in ["secondary"]:
                    if len(self.__matchD[rId]["matchedIds"]) == 1:
                        for mId, mD in self.__matchD[rId]["matchedIds"].items():
                            alignD["reference_database_accession"] = mId
                            isMatchedRefDb = True
                    elif taxIdL and len(taxIdL) == 1:
                        #  -- simplest match case --
                        numM = 0
                        for mId, mD in self.__matchD[rId]["matchedIds"].items():
                            if taxIdL[0] == mD["taxId"]:
                                alignD["reference_database_accession"] = mId
                                numM += 1
                        if numM == 1:
                            isMatchedRefDb = True
                    elif not taxIdL:
                        logger.info("%s no taxids with UniProt (%s) secondary mapping", entityKey, rId)
                    else:
                        logger.info("%s ambiguous mapping for a UniProt (%s) secondary mapping - taxIds %r", entityKey, rId, taxIdL)
                #
            except Exception:
                pass
        elif alignD["provenance_code"] in provSourceL and alignD["reference_database_name"] in refDbList:
            logger.info("%s leaving reference alignment for %s %s assigned by %r", entityKey, rId, alignD["reference_database_name"], provSourceL)
            isMatchedRefDb = False
            isMatchedAltDb = False
        else:
            logger.info("%s leaving a reference alignment for %s %s assigned by %r", entityKey, rId, alignD["reference_database_name"], alignD["provenance_code"])
        #
        logger.debug("%s isMatched %r isExcluded %r for alignment %r", entityKey, isMatchedRefDb, isMatchedAltDb, rId)
        return isMatchedRefDb, isMatchedAltDb, alignD, self.__hashAlignment(alignD)

    def __hashAlignment(self, aD):
        """
        Example:

            {'reference_database_name': 'UniProt', 'reference_database_accession': 'P62942', 'provenance_code': 'PDB',
              'aligned_regions': [{'entity_beg_seq_id': 1, 'ref_beg_seq_id': 1, 'length': 107}]}]
        """
        hsh = None
        hL = []
        try:
            hL.append(aD["reference_database_accession"])
            for aR in aD["aligned_regions"]:
                hL.append(aR["entity_beg_seq_id"])
                hL.append(aR["ref_beg_seq_id"])
                hL.append(aR["length"])
            hsh = tuple(hL)
        except Exception:
            pass
        return hsh

    def __getSiftsAccessions(self, entityKey, authAsymIdL):
        retL = []
        saoLD = self.__ssP.getLongestAlignments(entityKey[:4], authAsymIdL)
        for (_, dbAccession), _ in saoLD.items():
            retL.append({"database_name": "UniProt", "database_accession": dbAccession, "provenance_source": "SIFTS"})
        return retL

    def __getSiftsAlignments(self, entityKey, authAsymIdL):
        retL = []
        saoLD = self.__ssP.getLongestAlignments(entityKey[:4], authAsymIdL)
        for (_, dbAccession), saoL in saoLD.items():
            dD = {"reference_database_name": "UniProt", "reference_database_accession": dbAccession, "provenance_code": "SIFTS", "aligned_regions": []}
            for sao in saoL:
                dD["aligned_regions"].append({"ref_beg_seq_id": sao.getDbSeqIdBeg(), "entity_beg_seq_id": sao.getEntitySeqIdBeg(), "length": sao.getEntityAlignLength()})
            retL.append(dD)
        return retL

    def getReferenceAccessionAlignSummary(self):
        """ Summarize the alignment of PDB accession assignments with the current reference sequence database.
        """
        numPrimary = 0
        numSecondary = 0
        numNone = 0
        for _, mD in self.__matchD.items():
            if mD["matched"] == "primary":
                numPrimary += 1
            elif mD["matched"] == "secondary":
                numSecondary += 1
            else:
                numNone += 1
        logger.debug("Matched primary:  %d secondary: %d none %d", numPrimary, numSecondary, numNone)
        return numPrimary, numSecondary, numNone
