# Tests end to end — formation-gh-api

Ce module contient un test end to end (E2E) écrit en Java qui vérifie que
l'application déployée sur GitHub Pages à l'adresse
[https://aouzgaga.github.io/formation-gh-api/](https://aouzgaga.github.io/formation-gh-api/)
se charge correctement et ne renvoie aucune erreur.

## Scénarios testés

- la page d'accueil affiche bien les 3 utilisateurs de départ ;
- la page d'un utilisateur affiche son solde, permet de poser un congé,
  conserve les données après rechargement puis permet de supprimer le congé ;
- les trois fiches utilisateur sont consultables, un identifiant inconnu est signalé
  et les congés restent isolés par utilisateur ;
- une période ne contenant aucun jour ouvré est refusée ;
- les dates inversées et les chevauchements partiels ou complets sont refusés sans
  modifier les congés ni les soldes ; une période contiguë est acceptée ;
- une journée ouvrée et une période égale au solde disponible sont acceptées,
  tandis que le dépassement du solde est refusé ;
- les week-ends sont exclus du décompte et une période passée est acceptée ;
- une route inconnue affiche la page introuvable ;
- un mot de passe incorrect est refusé et l’absence de configuration du mot de
  passe E2E est signalée.

Le décompte actuel exclut uniquement les samedis et dimanches : aucun calendrier
de jours fériés n'est géré. Les dates passées ne sont pas bloquées par l'application.

## Technologies utilisées

- Java 17
- Maven
- [Selenium WebDriver](https://www.selenium.dev/) pour piloter le navigateur
- [WebDriverManager](https://github.com/bonigarcia/webdrivermanager) pour
  gérer automatiquement le driver Chrome (`chromedriver`)
- JUnit 5

## Prérequis

- Java 17+
- Maven 3.6+
- Google Chrome (ou Chromium) installé sur la machine

Si un `chromedriver` est déjà installé sur la machine (par exemple dans
`/usr/bin/chromedriver`), il est automatiquement réutilisé. Sinon,
WebDriverManager télécharge la version compatible avec le Chrome installé
(nécessite un accès réseau à `googlechromelabs.github.io`). Il est également
possible de forcer l'emplacement du driver via la variable d'environnement
`WEBDRIVER_CHROME_DRIVER`.

## Exécuter les tests

L'application requiert désormais un mot de passe. Pour l'exécution locale,
définissez la variable d'environnement `E2E_APP_PASSWORD` avec le mot de passe
de l'application. Pour GitHub Actions, configurez un secret de dépôt nommé
`E2E_APP_PASSWORD` ; le workflow le transmet aux tests sans l'inclure dans le
code source.

```bash
cd e2e-tests
read -s -p "Mot de passe de l'application : " E2E_APP_PASSWORD
export E2E_APP_PASSWORD
mvn test
```

## Rapports générés par la GitHub Action

Le workflow produit un rapport complet consultable **directement sur GitHub**,
sans avoir à télécharger de fichier ZIP :

- un résumé des scénarios (statuts, étapes réussies, durées) affiché
  directement dans le **Job Summary** de l'exécution GitHub Actions ;
- une page HTML (`index.html`) publiée sur **GitHub Pages** (lien ajouté dans
  le Job Summary lors des push sur `main`), affichant le détail des scénarios
  ainsi que les captures d'écran intégrées, avec des liens vers les livrables ;
- un fichier CSV des étapes de test exécutées ;
- un fichier Excel récapitulatif des cas de test et de leurs étapes ;
- un PV de recette métier au format Word (.docx) et PDF, directement réutilisable dans un document ou un mail de validation ;
- les captures d'écran des scénarios E2E.

Ces fichiers restent également disponibles en archive ZIP (artefact
`e2e-test-reports`) en sauvegarde, mais ce n'est plus nécessaire pour
consulter les résultats.
