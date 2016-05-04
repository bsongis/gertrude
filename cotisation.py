# -*- coding: utf-8 -*-

#    This file is part of Gertrude.
#
#    Gertrude is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 3 of the License, or
#    (at your option) any later version.
#
#    Gertrude is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with Gertrude; if not, see <http://www.gnu.org/licenses/>.

import math
from functions import *


class CotisationException(Exception):
    def __init__(self, errors):
        self.errors = errors
        
    def __str__(self):
        return '\n'.join(self.errors)


def GetDateRevenus(date):
    if creche.periode_revenus == REVENUS_CAFPRO:
        return datetime.date(date.year, date.month, 1)
    elif date >= datetime.date(2008, 9, 1):
        return datetime.date(date.year - 2, date.month, 1)
    elif date < datetime.date(date.year, 9, 1):
        return datetime.date(date.year - 2, 1, 1)
    else:
        return datetime.date(date.year - 1, 1, 1)


def GetNombreFacturesContrat(debut, fin):
    nombre_factures = 0
    date = debut
    while date <= fin:
        if IsContratFacture(date):
            nombre_factures += 1
        date = GetNextMonthStart(date)
    return nombre_factures


def GetNombreMoisSansFactureContrat(annee):
    result = 0
    if annee in creche.mois_sans_facture.keys():
        result += len(creche.mois_sans_facture[annee])
    if annee in creche.mois_facture_uniquement_heures_supp.keys():
        result += len(creche.mois_facture_uniquement_heures_supp[annee])
    return result    


def IsFacture(date):
    return date.year not in creche.mois_sans_facture.keys() or date.month not in creche.mois_sans_facture[date.year]


def IsContratFacture(date):
    return IsFacture(date) and (date.year not in creche.mois_facture_uniquement_heures_supp.keys() or date.month not in creche.mois_facture_uniquement_heures_supp[date.year])


def GetTranchesPaje(date, naissance, enfants_a_charge):
    if date < datetime.date(2016, 1, 1):
        if enfants_a_charge == 1:
            return [20285.0, 45077.01]
        elif enfants_a_charge == 2:
            return [23164.0, 51475.01]
        else:
            enfants_a_charge -= 3
            return [26043.0 + (enfants_a_charge * 2879.0), 57873.01 + (enfants_a_charge * 6398.0)]
    elif naissance >= datetime.date(2014, 4, 1):
        if enfants_a_charge == 1:
            return [20509.0, 45575.0]
        elif enfants_a_charge == 2:
            return [23420.0, 52044.0]
        else:
            enfants_a_charge -= 3
            return [23420.0 + (enfants_a_charge * 2911.0), 52044.01 + (enfants_a_charge * 6469.0)]
    else:
        if enfants_a_charge == 1:
            return [21332.0, 47405.0]
        elif enfants_a_charge == 2:
            return [24561.0, 54579.0]
        else:
            enfants_a_charge -= 3
            return [28435.0 + (enfants_a_charge * 3874.0), 63188 + (enfants_a_charge * 8609.0)]


class Cotisation(object):
    def CalculeFraisGarde(self, heures):
        return self.CalculeFraisGardeComplete(heures, heures)[0]
    
    def CalculeFraisGardeComplete(self, heures, heures_mois):
        if self.montant_heure_garde is not None:
            try:
                result = self.montant_heure_garde * heures
            except:
                result = 0.0
            tarifs = [self.montant_heure_garde]
        else:
            result = 0.0
            tarifs = set()
            heure = 0.0
            if heures_mois == 0:
                multiplier = 1
            else:
                multiplier = heures / heures_mois
            while heure < heures_mois:
                montant_heure_garde = creche.EvalTauxHoraire(self.mode_garde, self.inscrit.handicap, self.assiette_annuelle, self.enfants_a_charge, self.jours_semaine, self.heures_semaine, self.inscription.reservataire, self.inscrit.nom.lower(), self.parents, self.chomage, self.conge_parental, self.heures_mois, heure, self.tranche_paje, self.inscrit.famille.tarifs)
                result += multiplier * montant_heure_garde * min(1.0, heures_mois - heure)
                tarifs.add(montant_heure_garde)
                heure += 1.0
        return result, tarifs

    def __init__(self, inscrit, date, options=0):
        self.inscrit = inscrit
        self.date = date
        self.options = options
        errors = []
        if not inscrit.prenom or (not options & NO_NOM and not inscrit.nom):
            errors.append(u" - L'état civil de l'enfant est incomplet.")
        if date is None:
            errors.append(u" - La date de début de la période n'est pas renseignée.")
            raise CotisationException(errors)
        self.inscription = inscrit.GetInscription(date, preinscription=True)
        if self.inscription is None:
            errors.append(u" - Il n'y a pas d'inscription à cette date (%s)." % str(date))
            raise CotisationException(errors)

        self.debut = self.inscription.debut
        self.fin = self.inscription.fin
        self.fin_inscription = self.inscription.fin

        if creche.gestion_depart_anticipe and self.inscription.depart:
            self.fin = self.inscription.depart
            if options & DEPART_ANTICIPE:
                self.fin_inscription = self.inscription.depart

        if creche.facturation_periode_adaptation != PERIODE_ADAPTATION_FACTUREE_NORMALEMENT and self.inscription.fin_periode_adaptation:
            if self.inscription.IsInPeriodeAdaptation(self.date):
                self.fin = self.inscription.fin_periode_adaptation
            else:
                self.debut = self.inscription.fin_periode_adaptation + datetime.timedelta(1)
        
        if options & TRACES:
            print u"\nCotisation de %s au %s ..." % (GetPrenomNom(inscrit), date)

        self.revenus_parents = []
        self.liste_conges = []
        self.conges_inscription = []
        self.chomage = 0
        self.conge_parental = 0
        self.date_revenus = GetDateRevenus(self.date)
        self.assiette_annuelle = 0.0
        self.parents = 0
        self.frais_inscription = self.inscription.frais_inscription
        self.montant_allocation_caf = self.inscription.allocation_mensuelle_caf
        for parent in inscrit.famille.parents.values():
            if parent:
                self.parents += 1
                revenus_parent = Select(parent.revenus, self.date_revenus)
                are_revenus_needed = creche.AreRevenusNeeded()
                if are_revenus_needed and (revenus_parent is None or revenus_parent.revenu == ''):
                    errors.append(u" - Les déclarations de revenus de %s sont incomplètes." % parent.relation)
                elif revenus_parent:
                    if revenus_parent.revenu:
                        revenu = float(revenus_parent.revenu)
                    else:
                        revenu = 0.0
                    if creche.periode_revenus == REVENUS_CAFPRO:
                        revenu_debut, revenu_fin = revenus_parent.debut, revenus_parent.fin
                    elif self.date >= datetime.date(2008, 9, 1):
                        revenu_debut, revenu_fin = revenus_parent.debut, revenus_parent.fin
                        if isinstance(revenu_debut, datetime.date):
                            revenu_debut = datetime.date(revenu_debut.year + 2, revenu_debut.month, revenu_debut.day)
                        if isinstance(revenu_fin, datetime.date):
                            revenu_fin = datetime.date(revenu_fin.year + 2, revenu_fin.month, revenu_fin.day)
                    else:
                        revenu_debut, revenu_fin = (GetYearStart(self.date), GetYearEnd(self.date))
                    if are_revenus_needed:
                        self.AjustePeriode((revenu_debut, revenu_fin))
                    self.assiette_annuelle += revenu
                    if revenus_parent.chomage:
                        abattement = 0.3 * revenu
                        self.assiette_annuelle -= abattement
                        self.chomage += 1
                    else:
                        abattement = None
                    if revenus_parent.conge_parental:
                        self.conge_parental += 1
                    self.revenus_parents.append((parent, revenu, abattement))

        if options & TRACES:
            print u" assiette annuelle :", self.assiette_annuelle
            
        self.bareme_caf = Select(creche.baremes_caf, self.date)
        if self.bareme_caf:
            if self.bareme_caf.plafond and self.assiette_annuelle > self.bareme_caf.plafond:
                self.AjustePeriode(self.bareme_caf)
                self.assiette_annuelle = self.bareme_caf.plafond
                if options & TRACES:
                    print u" plafond CAF appliqué :", self.assiette_annuelle
            elif self.bareme_caf.plancher and self.assiette_annuelle < self.bareme_caf.plancher:
                self.AjustePeriode(self.bareme_caf)
                self.assiette_annuelle = self.bareme_caf.plancher
                if options & TRACES:
                    print u" plancher CAF appliqué :", self.assiette_annuelle
        else:
            if options & TRACES:
                print u" pas de barème CAF"
                    
        self.assiette_mensuelle = self.assiette_annuelle / 12
        
        if creche.modes_inscription == MODE_5_5:
            self.mode_garde = MODE_5_5  # TODO a renommer en mode_inscription
            self.jours_semaine = 5
            self.heures_reelles_semaine = 50.0
        else:
            self.mode_garde = self.inscription.mode
            self.jours_semaine, self.heures_reelles_semaine = self.inscription.GetJoursHeuresReference()
            self.semaines_reference = self.inscription.duree_reference / 7
            self.jours_semaine /= self.semaines_reference
            self.heures_reelles_semaine /= self.semaines_reference
        
        if self.mode_garde is None:
            errors.append(u" - Le mode de garde n'est pas renseigné.")
            
        if self.mode_garde == MODE_HALTE_GARDERIE:
            self.mode_inscription = MODE_HALTE_GARDERIE
        else:
            self.mode_inscription = MODE_CRECHE

        self.enfants_a_charge, self.enfants_en_creche, debut, fin = GetEnfantsCount(inscrit, self.date)
        self.AjustePeriode((debut, fin))
        
        if self.fin is None:
            self.fin = today + datetime.timedelta(2 * 365)

        if len(errors) > 0:
            raise CotisationException(errors)
        
        if options & TRACES:
            print u" période du %s au %s" % (self.debut, self.fin)
            print u" heures hebdomadaires (réelles) :", self.heures_reelles_semaine
        
        self.prorata_effectue = False
        self.heures_periode = 0.0
        self.heures_fermeture_creche = 0.0
        self.heures_accueil_non_facture = 0.0
        self.semaines_periode = 0
              
        if creche.mode_facturation == FACTURATION_FORFAIT_10H:
            self.heures_semaine = 10.0 * self.jours_semaine
            self.heures_mois = self.heures_semaine * 4
            self.heures_periode = self.heures_mois * 12
            self.nombre_factures = 12 - GetNombreMoisSansFactureContrat(self.date.year)
        elif creche.mode_facturation == FACTURATION_FORFAIT_MENSUEL:
            self.heures_semaine = self.heures_reelles_semaine
            self.heures_mois = self.heures_semaine * 4
            self.heures_periode = self.heures_mois * 12
            self.nombre_factures = 12 - GetNombreMoisSansFactureContrat(self.date.year)
        else:                
            self.heures_semaine = self.heures_reelles_semaine
            if creche.facturation_jours_feries == JOURS_FERIES_DEDUITS_ANNUELLEMENT:
                if self.fin_inscription is None:
                    errors.append(u" - La période d'inscription n'a pas de fin.")
                    raise CotisationException(errors)

                if creche.repartition == REPARTITION_MENSUALISATION_CONTRAT:
                    date = GetMonthStart(self.debut)
                else:
                    self.prorata_effectue = True
                    date = self.debut
                
                # debut_conge = None
                while date <= self.fin_inscription:
                    heures = self.inscription.GetJourneeReference(date).GetNombreHeures()
                    if heures:
                        if date in creche.jours_fermeture:
                            # if debut_conge is None:
                            #     debut_conge = date
                            if creche.jours_fermeture[date].options == ACCUEIL_NON_FACTURE:
                                if options & TRACES:
                                    print u' accueil non facturé :', date, "(%fh)" % heures
                                self.heures_accueil_non_facture += heures
                            else:
                                if options & TRACES:
                                    print u' jour de fermeture :', date, "(%fh)" % heures
                                self.heures_fermeture_creche += heures
                        elif date in inscrit.jours_conges:
                            if options & TRACES:
                                print u' jour de congé inscription :', date, "(%fh)" % heures
                            self.conges_inscription.append(date)
                            # if debut_conge is None:
                            #     debut_conge = date                            
                        else:
                            self.heures_periode += heures
                            # if debut_conge is not None:
                            #     self.liste_conges.append(date2str(debut_conge) + " - " + date2str(date-datetime.timedelta(1)))
                            #     debut_conge = None
                    date += datetime.timedelta(1)
                # if debut_conge is not None:
                #     self.liste_conges.append(date2str(debut_conge) + " - " + date2str(self.fin_inscription))
                if self.inscription.semaines_conges:
                    if options & TRACES:
                        print u' + %d semaines de congés' % self.inscription.semaines_conges
                    self.heures_periode -= self.inscription.semaines_conges * self.heures_semaine
                    self.liste_conges.append(u"%d semaines de congés" % self.inscription.semaines_conges)
                self.heures_periode = math.ceil(self.heures_periode)
                if options & TRACES:
                    print u' heures période :', self.heures_periode
                self.semaines_periode = 1 + (self.fin_inscription - self.inscription.debut).days / 7
                self.nombre_factures = GetNombreFacturesContrat(self.debut, self.fin_inscription)
                if self.nombre_factures == 0:
                    self.nombre_factures = 1
                if options & TRACES:
                    print u' nombres de factures :', self.nombre_factures
                # TODO pour Villefranche de Rouergue avec un paramètre supplémentaire
                # self.heures_mois = (self.heures_periode / self.nombre_factures)
                self.heures_mois = math.ceil(self.heures_periode / self.nombre_factures)
                if options & TRACES:
                    print u' heures mensuelles : %f (%f)' % (self.heures_mois, self.heures_periode / self.nombre_factures)
            else:
                if creche.repartition == REPARTITION_MENSUALISATION_CONTRAT_DEBUT_FIN_INCLUS:
                    if self.fin_inscription is None:
                        errors.append(u" - La période d'inscription n'a pas de fin.")
                        raise CotisationException(errors)
                    debut_inscription = self.inscription.debut
                    if creche.facturation_periode_adaptation == PERIODE_ADAPTATION_GRATUITE and self.inscription.fin_periode_adaptation:
                        debut_inscription = self.inscription.fin_periode_adaptation + datetime.timedelta(1)
                    self.semaines_periode = GetNombreSemainesPeriode(debut_inscription, self.fin_inscription)
                    self.nombre_factures = GetNombreFacturesContrat(debut_inscription, self.fin_inscription)
                    self.prorata_effectue = True
                elif creche.repartition == REPARTITION_MENSUALISATION_CONTRAT:
                    if self.fin_inscription is None:
                        errors.append(u" - La période d'inscription n'a pas de fin.")
                        raise CotisationException(errors)
                    self.semaines_periode = GetNombreSemainesPeriode(self.inscription.debut, self.fin_inscription)
                    self.nombre_factures = GetNombreFacturesContrat(self.inscription.debut, self.fin_inscription)
                elif creche.repartition == REPARTITION_SANS_MENSUALISATION:
                    if self.fin_inscription is None:
                        self.semaines_periode = 52
                        self.nombre_factures = 12 - GetNombreMoisSansFactureContrat(self.date.year)
                    else:
                        self.semaines_periode = GetNombreSemainesPeriode(self.inscription.debut, self.fin_inscription)
                        self.nombre_factures = GetNombreFacturesContrat(self.inscription.debut, self.fin_inscription)
                else:
                    self.semaines_periode = 52
                    self.nombre_factures = 12 - GetNombreMoisSansFactureContrat(self.date.year)
                if self.inscription.semaines_conges:
                    self.semaines_conges = self.inscription.semaines_conges
                else:
                    self.semaines_conges = 0
                self.heures_periode = (self.semaines_periode - self.semaines_conges) * self.heures_semaine
                if self.nombre_factures == 0:
                    self.heures_mois = 0
                else:
                    self.heures_mois = self.heures_periode / self.nombre_factures
                if options & TRACES:
                    print ' heures / periode : (%d-%f) * %f = %f' % (self.semaines_periode, self.semaines_conges, self.heures_semaine, self.heures_periode)
                    print ' nombre de factures : %d' % self.nombre_factures
                    print ' heures / mois : %f' % self.heures_mois
                
        if self.jours_semaine == 5:
            self.str_mode_garde = u'plein temps'
        else:
            self.str_mode_garde = u'%d/5èmes' % self.jours_semaine
        
        self.tranche_paje = 0
        self.taux_effort = None
        self.forfait_mensuel_heures = 0.0
        self.montants_heure_garde = []
        
        if creche.mode_facturation == FACTURATION_FORFAIT_MENSUEL:
            self.montant_heure_garde = 0.0
            self.cotisation_periode = 0.0
            self.cotisation_mensuelle = self.inscription.forfait_mensuel
        elif creche.mode_facturation == FACTURATION_HORAIRES_REELS or self.inscription.mode == MODE_FORFAIT_HORAIRE:
            if self.inscription.mode == MODE_FORFAIT_HORAIRE:
                self.forfait_mensuel_heures = self.inscription.forfait_mensuel_heures
            try:
                self.montant_heure_garde = creche.EvalTauxHoraire(self.mode_garde, inscrit.handicap, self.assiette_annuelle, self.enfants_a_charge, self.jours_semaine, self.heures_semaine, self.inscription.reservataire, inscrit.nom.lower(), self.parents, self.chomage, self.conge_parental, self.heures_mois, 0, self.tranche_paje, inscrit.famille.tarifs)
                if options & TRACES:
                    print " montant heure de garde (Forfait horaire) :", self.montant_heure_garde
            except Exception, e:
                print "Exception formule de calcul", e
                errors.append(u" - La formule de calcul du tarif horaire n'est pas correcte.")
                raise CotisationException(errors)
            self.cotisation_periode = None
            self.cotisation_mensuelle, self.montants_heure_garde = self.CalculeFraisGardeComplete(self.forfait_mensuel_heures, self.heures_mois)                    
        elif creche.mode_facturation == FACTURATION_PAJE:
            if not inscrit.naissance:
                errors.append(u" - La date de naissance n'est pas renseignée.")
                raise CotisationException(errors)
            self.tranche_paje = 1 + GetTranche(self.assiette_annuelle, GetTranchesPaje(date, inscrit.naissance, self.enfants_a_charge))
            if date < datetime.date(2016, 1, 1):
                self.AjustePeriode((debut, datetime.date(2015, 12, 31)))
            else:
                self.AjustePeriode((datetime.date(2016, 1, 1), fin))
            try:
                self.montant_heure_garde = creche.EvalTauxHoraire(self.mode_garde, inscrit.handicap, self.assiette_annuelle, self.enfants_a_charge, self.jours_semaine, self.heures_semaine, self.inscription.reservataire, inscrit.nom.lower(), self.parents, self.chomage, self.conge_parental, self.heures_mois, None, self.tranche_paje, inscrit.famille.tarifs)
                if options & TRACES:
                    print " montant heure de garde (PAJE) :", self.montant_heure_garde
            except:
                errors.append(u" - La formule de calcul du tarif horaire n'est pas correcte.")
                raise CotisationException(errors)
            if type(self.inscription.semaines_conges) == int:
                self.semaines_conges = self.inscription.semaines_conges
            else:                
                self.semaines_conges = 0
            self.cotisation_periode, self.montants_heure_garde = self.CalculeFraisGardeComplete(self.heures_periode, self.heures_mois)
            if options & TRACES:
                print " cotisation periode :", self.cotisation_periode
                print " montant heure garde supplementaire :", self.montant_heure_garde
            if self.nombre_factures == 0:
                self.cotisation_mensuelle = 0.0
            else:
                self.cotisation_mensuelle = self.cotisation_periode / self.nombre_factures
        elif creche.nom == u"LA VOLIERE":
            if self.enfants_a_charge == 1:
                tranche = GetTranche(self.assiette_annuelle, [20281.0, 45068.0])
            elif self.enfants_a_charge == 2:
                tranche = GetTranche(self.assiette_annuelle, [23350.0, 51889.0])
            elif self.enfants_a_charge == 3:
                tranche = GetTranche(self.assiette_annuelle, [27033.0, 60074.0])
            else:
                tranche = GetTranche(self.assiette_annuelle, [30716.0, 68259.0])
            B20 = creche.cout_journalier / 10
            B2X = B20 * (1.10, 1.15, 1.20)[tranche]
            self.a = (B20 - B2X) / 229
            self.b = (230 * B2X - B20) / 229
            self.montant_heure_garde = (self.a * self.heures_mois + self.b)
            self.cotisation_mensuelle = self.heures_mois * self.montant_heure_garde
        else:
            if self.enfants_a_charge > 1:
                self.mode_taux_effort = u'%d enfants à charge' % self.enfants_a_charge
            else:
                self.mode_taux_effort = u'1 enfant à charge'
                
            if creche.mode_facturation == FACTURATION_PSU_TAUX_PERSONNALISES:
                try:
                    self.taux_effort = creche.EvalTauxEffort(self.mode_garde, inscrit.handicap, self.assiette_annuelle, self.enfants_a_charge, self.jours_semaine, self.heures_semaine, self.inscription.reservataire, inscrit.nom.lower(), self.parents, self.chomage, self.conge_parental, self.heures_mois, 0, self.tranche_paje, inscrit.famille.tarifs)
                except Exception, e:
                    print "Exception formule de calcul", e
                    errors.append(u" - La formule de calcul du taux d'effort n'est pas correcte.")
                    raise CotisationException(errors)
            else:
                if creche.type == TYPE_PARENTAL and date.year < 2013:
                    tranche = self.enfants_a_charge
                    if inscrit.handicap:
                        tranche += 1
                    if tranche >= 4:
                        self.taux_effort = 0.02
                    elif tranche == 3:
                        self.taux_effort = 0.03
                    elif tranche == 2:
                        self.taux_effort = 0.04
                    else:
                        self.taux_effort = 0.05
                elif creche.type in (TYPE_FAMILIAL, TYPE_PARENTAL, TYPE_MICRO_CRECHE):
                    tranche = self.enfants_a_charge
                    if inscrit.handicap:
                        tranche += 1
                    if tranche > 5:
                        self.taux_effort = 0.02
                    elif tranche > 2:
                        self.taux_effort = 0.03
                    elif tranche == 2:
                        self.taux_effort = 0.04
                    else:
                        self.taux_effort = 0.05
                else:
                    tranche = self.enfants_a_charge
                    if inscrit.handicap:
                        tranche += 1
                    if tranche > 7:
                        self.taux_effort = 0.02
                    elif tranche > 3:
                        self.taux_effort = 0.03
                    elif tranche == 3:
                        self.taux_effort = 0.04
                    elif tranche == 2:
                        self.taux_effort = 0.05
                    else:
                        self.taux_effort = 0.06
            if options & TRACES:
                print u" taux d'effort :", self.taux_effort
                
            self.montant_heure_garde = self.assiette_mensuelle * self.taux_effort / 100
            if creche.mode_facturation in (FACTURATION_PSU, FACTURATION_PSU_TAUX_PERSONNALISES):
                self.montant_heure_garde = round(self.montant_heure_garde, 2)
                self.cotisation_mensuelle = self.heures_mois * self.montant_heure_garde
            else:
                self.cotisation_mensuelle = self.assiette_mensuelle * self.taux_effort * self.heures_mois / 100
        
        if creche.facturation_periode_adaptation != PERIODE_ADAPTATION_FACTUREE_NORMALEMENT and self.inscription.IsInPeriodeAdaptation(self.date):
            self.cotisation_periode = 0.0
            self.cotisation_mensuelle = 0.0
        
        self.majoration_mensuelle = 0.0
        self.majoration_journaliere = 0.0
        self.raison_majoration_journaliere = set()
        if self.montant_heure_garde is not None:
            for tarif in creche.tarifs_speciaux:
                if inscrit.famille.tarifs & (1 << tarif.idx):
                    heure_garde_diff = 0.0
                    jour_garde_diff = 0.0
                    if tarif.unite == TARIF_SPECIAL_UNITE_EUROS:
                        cotisation_diff = tarif.valeur
                    elif tarif.unite == TARIF_SPECIAL_UNITE_POURCENTAGE:
                        cotisation_diff = (self.cotisation_mensuelle * tarif.valeur) / 100
                        heure_garde_diff = (self.montant_heure_garde * tarif.valeur) / 100
                    elif tarif.unite == TARIF_SPECIAL_UNITE_EUROS_PAR_HEURE:
                        cotisation_diff = tarif.valeur * self.heures_mois 
                        heure_garde_diff = tarif.valeur
                    elif tarif.unite == TARIF_SPECIAL_UNITE_EUROS_PAR_JOUR:
                        cotisation_diff = 0
                        jour_garde_diff = tarif.valeur
                        self.raison_majoration_journaliere.add(tarif.label)
                    else:
                        errors.append(u" - Le tarif spécial à appliquer n'est pas implémenté.")
                        raise CotisationException(errors)
                    
                    if tarif.type == TARIF_SPECIAL_REDUCTION:
                        self.majoration_mensuelle -= cotisation_diff
                        self.montant_heure_garde -= heure_garde_diff
                        self.majoration_journaliere -= jour_garde_diff
                    elif tarif.type == TARIF_SPECIAL_MAJORATION:
                        self.majoration_mensuelle += cotisation_diff
                        self.montant_heure_garde += heure_garde_diff
                        self.majoration_journaliere += jour_garde_diff
                    else:
                        self.cotisation_mensuelle = cotisation_diff
                        self.montant_heure_garde = heure_garde_diff
                    
        self.cotisation_mensuelle += self.majoration_mensuelle
        
        if creche.arrondi_mensualisation_euros == ARRONDI_EURO_PLUS_PROCHE:
            self.cotisation_mensuelle = round(self.cotisation_mensuelle)

        if options & TRACES: 
            print " cotisation mensuelle :", self.cotisation_mensuelle
            print " montant heure garde :", self.montant_heure_garde

        if options & TRACES:
            print
    
    def AjustePeriode(self, param):
        if isinstance(param, tuple):
            debut, fin = param
        else:
            debut, fin = param.debut, param.fin
        if debut and debut > self.debut:
            self.debut = debut
        if fin and fin > self.debut and (not self.fin or fin < self.fin):
            self.fin = fin
            
    def Include(self, date):
        return self.debut <= date <= self.fin
